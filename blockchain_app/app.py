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
                return redirect(url_for("dashboard")) # Chuyển hướng producer tới dashboard mới
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
#  DASHBOARD
# ════════════════════════════════════════════════════════════════
@app.route("/dashboard")
@login_required(role="producer")
def dashboard():
    sub_role = session.get("sub_role")
    user = session.get("user")
    
    # Ánh xạ vai trò tới trạng thái (event_type) trước đó mà họ cần xử lý
    # Ví dụ: 'roaster' cần xử lý các lô đã 'PROCESSING' xong
    prereq_event_map = {
        "processor": "HARVEST",
        "roaster": "PROCESSING",
        "distributor": "ROASTING",
        "retailer": "DISTRIBUTION",
    }

    todo_products = []
    # Nông dân không có "todo list" từ người khác, họ là người bắt đầu chuỗi
    if sub_role in prereq_event_map:
        required_prev_event = prereq_event_map[sub_role]
        
        # Lấy tất cả các product_id duy nhất
        all_product_ids = bc.get_all_product_ids()
        
        for pid in all_product_ids:
            # Lấy block cuối cùng của sản phẩm
            last_block = bc.get_last_block(pid)
            if last_block and last_block.data.get("event_type") == required_prev_event:
                # Nếu trạng thái cuối cùng khớp với yêu cầu, thêm vào to-do list
                product_name = last_block.data.get("details", {}).get("product_name", pid)
                todo_products.append({
                    "product_id": pid,
                    "product_name": product_name,
                    "last_event": EVENT_TYPES.get(required_prev_event, required_prev_event),
                    "last_actor": last_block.data.get("actor")
                })

    return render_template("dashboard.html", 
                           sub_role=sub_role,
                           role_label=ROLE_LABELS.get(sub_role, "Nhà sản xuất"),
                           todo_products=todo_products)


# ════════════════════════════════════════════════════════════════
#  PRODUCER — Thêm sự kiện
# ════════════════════════════════════════════════════════════════
@app.route("/producer", methods=["GET", "POST"])
@login_required(role="producer")
def producer():
    sub_role = session.get("sub_role")
    if not sub_role:
        flash('Thông tin vai trò phụ (sub_role) không tồn tại. Vui lòng đăng nhập lại.', 'danger')
        return redirect(url_for('login_role', role='producer'))

    user = session.get("user")
    product_id_from_url = request.args.get('product_id')
    
    # --- Định nghĩa Máy trạng thái (State Machine) ---
    # 1. Ánh xạ vai trò tới hành động họ có thể thực hiện
    role_to_event = {
        "farmer": "HARVEST",
        "processor": "PROCESSING",
        "roaster": "ROASTING",
        "distributor": "DISTRIBUTION",
        "retailer": "RETAIL",
    }

    # 2. Ánh xạ trạng thái hiện tại -> trạng thái tiếp theo
    state_transition = {
        "HARVEST": "PROCESSING",
        "PROCESSING": "ROASTING",
        "ROASTING": "DISTRIBUTION",
        "DISTRIBUTION": "RETAIL",
    }

    # --- XỬ LÝ POST REQUEST (Khi người dùng gửi form) ---
    if request.method == 'POST':
        event_type = request.form.get('event_type') # Lấy từ trường ẩn
        product_id = request.form.get("product_id", "").strip().upper()

        # 1. Kiểm tra quyền thực hiện hành động dựa trên vai trò
        allowed_event_for_role = role_to_event.get(sub_role)
        if event_type != allowed_event_for_role:
            flash(f"❌ Vai trò '{ROLE_LABELS.get(sub_role)}' không được phép thực hiện hành động '{EVENT_TYPES.get(event_type)}'.", "danger")
            return redirect(url_for('producer', product_id=product_id))

        # 2. Kiểm tra tính hợp lệ của quy trình (state machine) cho sản phẩm đã có
        if product_id and event_type != 'HARVEST':
            last_block = bc.get_last_block(product_id)
            if not last_block:
                 flash(f"❌ Không tìm thấy sản phẩm với ID '{product_id}'.", "danger")
                 return redirect(url_for('dashboard'))
            
            expected_next_event = state_transition.get(last_block.data.get("event_type"))
            if event_type != expected_next_event:
                flash(f"❌ Hành động không hợp lệ. Bước tiếp theo dự kiến là '{EVENT_TYPES.get(expected_next_event)}'.", "danger")
                return redirect(url_for('producer', product_id=product_id))

        # 3. Thu thập dữ liệu chi tiết từ form
        details = {}
        if event_type == 'HARVEST':
            if not product_id:
                date_str = datetime.now().strftime("%Y%m%d")
                count = len(bc.get_blocks_by_event("HARVEST"))
                product_id = f"ARB-CD-{date_str}-{count+1:03d}"
            farm_name = request.form.get('farm_name')
            coffee_variety = request.form.get('coffee_variety')
            details = {
                "product_name": f"{coffee_variety} - {farm_name}", "farm_name": farm_name, "coffee_variety": coffee_variety,
                "region": request.form.get('region'), "altitude": request.form.get('altitude'),
                "planting_date": request.form.get('planting_date'), "harvest_date": request.form.get('harvest_date'),
            }
        elif event_type == 'PROCESSING':
            details = { "processing_method": request.form.get('processing_method'), "fermentation_time_hours": request.form.get('fermentation_time_hours'), "drying_method": request.form.get('drying_method'), "moisture_percentage": request.form.get('moisture_percentage'), "processing_date": request.form.get('processing_date'), }
        elif event_type == 'ROASTING':
            details = { "roast_level": request.form.get('roast_level'), "roast_date": request.form.get('roast_date'), "roast_temperature_celsius": request.form.get('roast_temperature_celsius'), "roastery_name": request.form.get('roastery_name'), "packaging_date": request.form.get('packaging_date'), }
        elif event_type == 'DISTRIBUTION':
            details = { "shipment_id": request.form.get('shipment_id'), "delivery_date": request.form.get('delivery_date'), "warehouse_location": request.form.get('warehouse_location'), "delivery_status": request.form.get('delivery_status'), }
        elif event_type == 'RETAIL':
            details = { "shop_name": request.form.get('shop_name'), "receive_date": request.form.get('receive_date'), "product_status": request.form.get('product_status'), }

        if not product_id:
            flash("Lỗi: Product ID không được tạo hoặc cung cấp.", "danger")
            return redirect(url_for('producer'))

        # 4. Xử lý bằng chứng (file upload)
        MANDATORY_PROOF_EVENTS = ["PROCESSING", "ROASTING"]
        file = request.files.get('proof_file')
        if event_type in MANDATORY_PROOF_EVENTS and (not file or file.filename == ''):
            flash(f"❌ Lỗi: Giai đoạn '{EVENT_TYPES.get(event_type)}' yêu cầu phải có tệp bằng chứng.", "danger")
            return redirect(url_for('producer', product_id=product_id))

        # 5. Tạo dữ liệu block và thêm vào blockchain
        new_data = {
            "product_id": product_id, "event_type": event_type, "event_name": EVENT_TYPES.get(event_type, "Không rõ"),
            "actor": user, "timestamp": datetime.now().isoformat(),
            "details": {k: v for k, v in details.items() if v}, "proofs": []
        }

        if file and file.filename != '':
            filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_data['proofs'].append(filename)

        try:
            bc.add_block(new_data)
            flash(f'✅ Thêm sự kiện "{EVENT_TYPES.get(event_type)}" cho sản phẩm {product_id} thành công!', 'success')
            return redirect(url_for('dashboard'))
        except ValueError as e:
            flash(f"❌ Lỗi khi thêm block: {e}", "danger")
            return redirect(url_for('producer', product_id=product_id))

    # --- XỬ LÝ GET REQUEST (Khi tải trang) ---
    next_event_type = None
    product_info = {}
    
    if product_id_from_url:
        # Sản phẩm đã có -> tìm hành động tiếp theo
        last_block = bc.get_last_block(product_id_from_url)
        if last_block:
            last_event_type = last_block.data.get("event_type")
            next_event_type = state_transition.get(last_event_type)
            # Lấy thông tin để điền sẵn vào form
            trace = bc.get_trace(product_id_from_url)
            for block in trace:
                product_info.update(block.data.get("details", {}))
            product_info['product_id'] = product_id_from_url
        else:
            flash(f"Không tìm thấy sản phẩm với ID {product_id_from_url}.", "warning")
            return redirect(url_for('dashboard'))
    else:
        # Sản phẩm mới -> chỉ có thể là Thu hoạch
        next_event_type = "HARVEST"

    # Kiểm tra xem vai trò của người dùng có khớp với hành động tiếp theo không
    allowed_event_for_role = role_to_event.get(sub_role)
    current_event = None
    if next_event_type == allowed_event_for_role:
        current_event = next_event_type # Chỉ cho phép hành động nếu vai trò và trạng thái khớp
        
    return render_template('producer.html', 
                           user=user, 
                           product_id=product_id_from_url, 
                           current_event=current_event,
                           event_type_labels=EVENT_TYPES,
                           product_info=product_info,
                           sub_role=sub_role,
                           role_label=ROLE_LABELS.get(sub_role, "Nhà sản xuất"))


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