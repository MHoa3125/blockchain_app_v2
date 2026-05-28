from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from blockchain import Blockchain
import qrcode
import io
import base64
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import os
from werkzeug.utils import secure_filename

from bson.objectid import ObjectId


app = Flask(__name__)
app.secret_key = "blockchain_doAn_2026_secret"

# ── Cấu hình thư mục upload ─────────────────────────────────────
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Tự động tạo thư mục nếu chưa có

# ── Khởi tạo blockchain (kết nối MongoDB) ───────────────────────
bc = Blockchain()
users_collection = bc.db['users'] # Collection for users

# ── Tài khoản hardcode (ĐÃ LỖI THỜI) ───────────────────────────
# Dữ liệu người dùng giờ được quản lý trong MongoDB collection 'users'
# USERS = { ... }


# -- Constants --
# Định nghĩa các loại sự kiện và vai trò cho dễ quản lý
EVENT_TYPES = {
    "HARVEST": "Thu hoạch (Nông hộ)",
    "PROCESSING": "Sơ chế (Đơn vị sơ chế)",
    "ROASTING": "Rang xay (Xưởng rang)",
    "DISTRIBUTION": "Phân phối (Nhà phân phối)",
    "RETAIL": "Bán lẻ (Quán cà phê)",
}

# Ánh xạ vai trò phụ tới các loại sự kiện được phép
ROLE_EVENT_TYPES = {
    "farmer":     ["HARVEST"],
    "processor":  ["PROCESSING"],
    "roaster":    ["ROASTING"],
    "distributor":["DISTRIBUTION"],
    "retailer":   ["RETAIL"],
}

ROLE_LABELS = {
    "farmer":     "Nông hộ trồng cà phê",
    "processor":  "Đơn vị sơ chế",
    "roaster":    "Xưởng rang xay",
    "distributor":"Đơn vị phân phối",
    "retailer":   "Quán cà phê",
}

CATEGORIES = ["Rau củ", "Trái cây", "Thịt sạch", "Thủy sản", "Khác"]

# ── Helper: tạo QR base64 từ product_id ──────────────────────────
def make_qr_base64(product_id: str) -> str:
    """
    Tạo mã QR chứa URL đầy đủ để truy cập từ mạng nội bộ.
    Ví dụ: http://192.168.1.10:5000/trace/SP20260413-001
    """
    # Lấy địa chỉ IP của request để tạo URL động
    # Điều này giúp mã QR luôn đúng dù IP của bạn thay đổi
    base_url = request.host_url.replace("127.0.0.1", request.host.split(':')[0])
    url = f"{base_url}trace?product_id={product_id}"
    
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

# ── Decorator phân quyền ──────────────────────────────────────────
def login_required(role=None):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                flash("Vui lòng đăng nhập.", "warning")
                return redirect(url_for("index"))
            if role and session.get("role") != role:
                flash("Bạn không có quyền truy cập trang này.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ════════════════════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════════════════════
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", user=session.get("user"), role=session.get("role"))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/login/<role>", methods=["GET", "POST"])
def login_role(role):
    # Kiểm tra xem vai trò có hợp lệ không
    if role not in ["producer", "consumer", "admin"]:
        flash("Vai trò không hợp lệ.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = users_collection.find_one({"username": username})

        # Xác thực username, password (đã hash) và vai trò phải khớp với URL
        if user and check_password_hash(user["password_hash"], password) and user["role"] == role:
            session["user"] = user["username"]
            session["role"] = user["role"]
            session["sub_role"] = user.get("sub_role")

            flash(f"Đăng nhập thành công với vai trò {role}!", "success")

            # Chuyển hướng đến trang tương ứng
            if role == "producer":
                return redirect(url_for("producer"))
            elif role == "admin":
                return redirect(url_for("admin"))
            else: # consumer
                return redirect(url_for("trace"))
        
        flash("Sai tài khoản, mật khẩu hoặc vai trò không đúng.", "danger")

    # Render template với vai trò tương ứng cho GET request
    return render_template("login.html", role=role, role_labels=ROLE_LABELS)


@app.route("/logout")
def logout():
    session.clear()
    flash("Đã đăng xuất.", "info")
    return redirect(url_for("index"))


# ════════════════════════════════════════════════════════════════
#  PRODUCER — Thêm sự kiện
# ════════════════════════════════════════════════════════════════
@app.route("/producer", methods=["GET", "POST"])
@login_required(role="producer")
def producer():
    sub_role = session.get("sub_role", "producer")
    allowed_event_types = ROLE_EVENT_TYPES.get(sub_role, [])
    role_label = ROLE_LABELS.get(sub_role, "Nhà sản xuất")

    # Lấy danh sách sản phẩm do người dùng (nông dân) tạo ra
    user_products = []
    if sub_role == "producer": # Chỉ nông dân mới thấy
        genesis_blocks = bc.get_blocks_by_event_and_actor("FARMING", session["user"])
        for block in genesis_blocks:
            product_id = block.data.get("product_id")
            if product_id:
                user_products.append({
                    "product_id": product_id,
                    "product_name": block.data.get("details", {}).get("product_name", "N/A"),
                    "qr_code": make_qr_base64(product_id)
                })

    # Lấy thông tin chi tiết nếu có product_id trên URL (để fill form)
    product_info = {}
    product_id_from_url = request.args.get('product_id', '').strip().upper()
    if product_id_from_url:
        trace = bc.get_trace(product_id_from_url)
        if trace:
            for block in trace:
                # Ưu tiên cập nhật từ 'details' nếu có
                product_info.update(block.data.get("details", {}))
        
        # FIX TRIỆT ĐỂ: Luôn thêm product_id vào dict để template sử dụng
        # Dòng này áp dụng cho mọi vai trò khi cập nhật
        product_info['product_id'] = product_id_from_url

    if request.method == "POST":
        event_type = request.form.get("event_type")

        if event_type not in allowed_event_types:
            flash(f"❌ Vai trò '{role_label}' không được phép thực hiện hành động này.", "danger")
            return redirect(url_for('producer'))

        details = {}
        product_id = request.form.get("product_id", "").strip().upper()

        # --- Xây dựng `details` cho từng loại sự kiện ---
        if event_type == 'HARVEST':
            if not product_id:
                date_str = datetime.now().strftime("%Y%m%d")
                count = len(bc.get_blocks_by_event("HARVEST"))
                product_id = f"ARB-CD-{date_str}-{count+1:03d}" # Mã mới
            
            farm_name = request.form.get('farm_name')
            coffee_variety = request.form.get('coffee_variety')
            
            details = {
                "product_name": f"{coffee_variety} - {farm_name}", # Tự động tạo tên sản phẩm
                "farm_name": farm_name,
                "coffee_variety": coffee_variety,
                "region": request.form.get('region'),
                "altitude": request.form.get('altitude'),
                "planting_date": request.form.get('planting_date'),
                "harvest_date": request.form.get('harvest_date'),
            }
        elif event_type == 'PROCESSING':
            details = {
                "processing_method": request.form.get('processing_method'),
                "fermentation_time_hours": request.form.get('fermentation_time_hours'),
                "drying_method": request.form.get('drying_method'),
                "moisture_percentage": request.form.get('moisture_percentage'),
                "processing_date": request.form.get('processing_date'),
            }
        elif event_type == 'ROASTING':
            details = {
                "roast_level": request.form.get('roast_level'),
                "roast_date": request.form.get('roast_date'),
                "roast_temperature_celsius": request.form.get('roast_temperature_celsius'),
                "roastery_name": request.form.get('roastery_name'),
                "packaging_date": request.form.get('packaging_date'),
            }
        elif event_type == 'DISTRIBUTION':
            details = {
                "shipment_id": request.form.get('shipment_id'),
                "delivery_date": request.form.get('delivery_date'),
                "warehouse_location": request.form.get('warehouse_location'),
                "delivery_status": request.form.get('delivery_status'),
            }
        elif event_type == 'RETAIL':
            details = {
                "shop_name": request.form.get('shop_name'),
                "receive_date": request.form.get('receive_date'),
                "product_status": request.form.get('product_status'),
            }

        if not product_id:
            flash("Vui lòng điền Product ID.", "danger")
            return redirect(url_for('producer'))

        # --- Kiểm tra bằng chứng bắt buộc ---
        MANDATORY_PROOF_EVENTS = ["PROCESSING", "ROASTING"]
        file = request.files.get('proof_file')

        if event_type in MANDATORY_PROOF_EVENTS and (not file or file.filename == ''):
            flash(f"❌ Lỗi: Giai đoạn '{EVENT_TYPES.get(event_type)}' yêu cầu phải có tệp bằng chứng.", "danger")
            # Chuyển hướng trở lại trang producer với product_id đã nhập để không phải gõ lại
            return redirect(url_for('producer', product_id=product_id))

        # Cấu trúc dữ liệu mới cho block
        new_data = {
            "product_id": product_id,
            "event_type": event_type,
            "event_name": EVENT_TYPES.get(event_type, "Không rõ"),
            "actor": session["user"],
            "timestamp": datetime.now().isoformat(),
            "details": {k: v for k, v in details.items() if v}, # Chỉ lưu các giá trị không rỗng
            "proofs": [] # Sẽ được cập nhật bên dưới
        }

        # Xử lý file upload làm bằng chứng (nếu có)
        if file and file.filename != '':
            # Tạo tên file an toàn và độc nhất (bằng cách thêm timestamp)
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_data['proofs'].append(filename)

        try:
            block = bc.add_block(new_data)
            flash(f"✅ Đã thêm block #{block.index} cho sản phẩm {product_id}.", "success")
            return redirect(url_for('producer', product_id=product_id))
        except ValueError as e:
            flash(f"❌ Lỗi: {e}", "danger")

    return render_template("producer.html",
                           allowed_event_types=allowed_event_types,
                           event_type_labels=EVENT_TYPES,
                           categories=CATEGORIES,
                           form={},
                           role_label=role_label,
                           sub_role=sub_role,
                           product_info=product_info,
                           user_products=user_products)


# ════════════════════════════════════════════════════════════════
#  CONSUMER — Tra cứu sản phẩm
# ════════════════════════════════════════════════════════════════
@app.route("/trace", methods=["GET"])
def trace():
    product_id = request.args.get("product_id", "").strip().upper()
    blocks = []
    product_info = {}
    qr_b64 = None
    not_found = False

    if product_id:
        found_blocks = bc.get_trace(product_id)
        if found_blocks:
            blocks = found_blocks
            qr_b64 = make_qr_base64(product_id)
            # Tổng hợp thông tin từ tất cả các block vào một dict duy nhất
            for block in blocks:
                # Ưu tiên cập nhật từ 'details' nếu có, nếu không thì lấy từ data
                details = block.data.get("details", {})
                if details:
                    product_info.update(details)
                else:
                    # Fallback cho cấu trúc dữ liệu cũ
                    product_info.update({k: v for k, v in block.data.items() if k not in ['product_id', 'event', 'actor', 'timestamp', 'event_type', 'event_name', 'details', 'proofs']})

        else:
            not_found = True

    return render_template("trace.html",
                           product_id=product_id,
                           blocks=blocks,
                           product_info=product_info,
                           qr_b64=qr_b64,
                           not_found=not_found,
                           stages=list(EVENT_TYPES.values()))


# ── Route để phục vụ file đã upload ───────────────────────────────
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)



# ════════════════════════════════════════════════════════════════
#  ADMIN — Dashboard, Validate, Tamper
# ════════════════════════════════════════════════════════════════
@app.route("/admin")
@login_required(role="admin")
def admin():
    all_blocks = [b.to_dict() for b in bc.get_all_blocks()]
    users = list(users_collection.find().sort("username", 1))
    return render_template("admin.html", blocks=all_blocks, users=users)


# ───────────────── USER MANAGEMENT (CRUD) ──────────────────
@app.route("/admin/users/add", methods=["GET", "POST"])
@login_required(role="admin")
def add_user():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password").strip()
        role = request.form.get("role")
        sub_role = request.form.get("sub_role") if role == "producer" else None
        full_name = request.form.get("full_name").strip()

        if not username or not password or not full_name:
            flash("Vui lòng điền đầy đủ các trường bắt buộc.", "danger")
            return render_template("user_form.html", user=request.form)

        if users_collection.find_one({"username": username}):
            flash("Tên đăng nhập đã tồn tại.", "danger")
            return render_template("user_form.html", user=request.form)

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        new_user = {
            "username": username,
            "password_hash": hashed_password,
            "role": role,
            "sub_role": sub_role,
            "full_name": full_name,
            "created_at": datetime.now()
        }
        users_collection.insert_one(new_user)
        flash(f"Đã tạo người dùng '{username}' thành công.", "success")
        return redirect(url_for("admin"))

    return render_template("user_form.html")


@app.route("/admin/users/edit/<user_id>", methods=["GET", "POST"])
@login_required(role="admin")
def edit_user(user_id):
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        flash("Không tìm thấy người dùng.", "danger")
        return redirect(url_for("admin"))

    if request.method == "POST":
        password = request.form.get("password").strip()
        role = request.form.get("role")
        sub_role = request.form.get("sub_role") if role == "producer" else None
        full_name = request.form.get("full_name").strip()

        update_data = {
            "role": role,
            "sub_role": sub_role,
            "full_name": full_name
        }

        if password:
            update_data["password_hash"] = generate_password_hash(password, method='pbkdf2:sha256')

        users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
        flash(f"Đã cập nhật người dùng '{user['username']}'.", "success")
        return redirect(url_for("admin"))

    return render_template("user_form.html", user=user)


@app.route("/admin/users/delete/<user_id>", methods=["POST"])
@login_required(role="admin")
def delete_user(user_id):
    user_to_delete = users_collection.find_one({"_id": ObjectId(user_id)})
    
    # Prevent admin from deleting themselves
    if user_to_delete and user_to_delete["username"] == session.get("user"):
        flash("Bạn không thể xóa chính mình.", "danger")
        return redirect(url_for("admin"))

    users_collection.delete_one({"_id": ObjectId(user_id)})
    flash("Đã xóa người dùng.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/validate")
@login_required(role="admin")
def validate():
    bc.reset()  # Tải lại chain từ DB trước khi kiểm tra
    valid, message = bc.is_valid()
    return jsonify({"valid": valid, "message": message})


@app.route("/admin/tamper", methods=["POST"])
@login_required(role="admin")
def tamper():
    """
    ═══════════════════════════════════════════════════════════════
    Demo tamper: sửa location của block được chọn thành '[TAMPERED]'
    Sau đó is_valid() sẽ trả về False.
    ═══════════════════════════════════════════════════════════════
    """
    index = int(request.form.get("index", 1))
    if index > 0:
        bc.tamper(index)
        flash(f"Block {index} đã bị thay đổi. Hãy kiểm tra lại chuỗi.", "warning")
    return redirect(url_for("admin"))

@app.route("/admin/reset", methods=["POST"])
@login_required(role="admin")
def reset_chain():
    """
    Xóa toàn bộ blockchain.
    """
    bc.delete_all_blocks()
    flash("✅ Toàn bộ blockchain đã được xóa sạch!", "success")
    return redirect(url_for("admin"))

# =================== ONE-TIME ADMIN CREATION ===================
@app.route("/create-admin")
def create_admin():
    """
    Chạy route này một lần để tạo người dùng quản trị ban đầu.
    Vì lý do bảo mật, route này nên được xóa sau lần chạy đầu tiên.
    """
    # Kiểm tra xem quản trị viên đã tồn tại chưa
    if users_collection.find_one({"username": "quantrivien"}):
        return "Tài khoản quản trị viên đã tồn tại."

    # Hash the password
    hashed_password = generate_password_hash("quantri123", method='pbkdf2:sha256')

    # Tạo người dùng quản trị
    users_collection.insert_one({
        "username": "quantrivien",
        "password_hash": hashed_password,
        "role": "admin",
        "full_name": "Quản Trị Viên",
        "created_at": datetime.now()
    })

    return "Tài khoản quản trị viên 'quantrivien' đã được tạo thành công!"
# ===============================================================

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')