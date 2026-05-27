from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from blockchain import Blockchain
import qrcode
import io
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = "blockchain_doAn_2026_secret"

# ── Khởi tạo blockchain (kết nối MongoDB) ───────────────────────
bc = Blockchain()

# ── Tài khoản hardcode ────────────────────────────────────────────
USERS = {
    "nongtrai_dalat": {
        "password": "nt123",
        "role": "producer",
        "sub_role": "producer"  # Vai trò phụ được gán cứng
    },
    "vanchuyen_hcm": {
        "password": "vc123",
        "role": "producer",
        "sub_role": "transporter" # Vai trò phụ được gán cứng
    },
    "sieuthi_saigon": {
        "password": "st123",
        "role": "producer",
        "sub_role": "retailer"    # Vai trò phụ được gán cứng
    },
    "consumer":    {"password": "cons123",  "role": "consumer"},
    "admin":       {"password": "admin123", "role": "admin"},
}

# -- Constants --
# Định nghĩa các loại sự kiện và vai trò cho dễ quản lý
EVENT_TYPES = {
    "FARMING": "Trồng & Thu hoạch",
    "PACKAGING": "Đóng gói & Kiểm định",
    "TRANSPORT": "Vận chuyển",
    "DISTRIBUTION": "Phân phối",
    "RETAIL": "Bán lẻ / Điểm bán",
}

# Ánh xạ vai trò phụ tới các loại sự kiện được phép
ROLE_EVENT_TYPES = {
    "producer":    ["FARMING", "PACKAGING"],
    "transporter": ["TRANSPORT"],
    "retailer":    ["DISTRIBUTION", "RETAIL"],
}

ROLE_LABELS = {
    "producer":    "Nhà sản xuất",
    "transporter": "Vận chuyển",
    "retailer":    "Đại lý / Bán lẻ",
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


@app.route("/login/<role>", methods=["GET", "POST"])
def login_role(role):
    # Kiểm tra xem vai trò có hợp lệ không
    if role not in ["producer", "consumer", "admin"]:
        flash("Vai trò không hợp lệ.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        user_data = USERS.get(username)
        
        # Xác thực username, password và vai trò phải khớp với URL
        if user_data and user_data["password"] == password and user_data["role"] == role:
            session["user"] = username
            session["role"] = user_data["role"]
            
            # Tự động gán sub_role từ dữ liệu người dùng đã được định nghĩa sẵn
            session["sub_role"] = user_data.get("sub_role") # Lấy sub_role gán cứng


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
        if event_type == 'FARMING':
            if not product_id:
                date_str = datetime.now().strftime("%Y%m%d")
                count = len(bc.get_blocks_by_event("FARMING"))
                product_id = f"SP{date_str}-{count+1:03d}"
            details = {
                "product_name": request.form.get('product_name'),
                "quantity": request.form.get('quantity'),
                "unit": request.form.get('unit'),
                "farm_id": request.form.get('farm_id')
            }
        elif event_type == 'TRANSPORT':
            details = {
                "vehicle_id": request.form.get('vehicle_id'),
                "temperature_celsius": request.form.get('temperature_celsius'),
                "departure_time": request.form.get('departure_time')
            }
        elif event_type == 'PACKAGING':
            details = {
                "packaging_date": request.form.get('packaging_date'),
                "quality_certificate": request.form.get('quality_certificate'),
                "lot_number": request.form.get('lot_number')
            }
        elif event_type == 'DISTRIBUTION':
            details = {
                "distributor_name": request.form.get('distributor_name'),
                "arrival_date": request.form.get('arrival_date'),
                "storage_condition": request.form.get('storage_condition')
            }
        elif event_type == 'RETAIL':
            details = {
                "shelf_date": request.form.get('shelf_date'),
                "store_location": request.form.get('store_location'),
                "batch_code": request.form.get('batch_code')
            }

        if not product_id:
            flash("Vui lòng điền Product ID.", "danger")
            return redirect(url_for('producer'))

        # Cấu trúc dữ liệu mới cho block
        new_data = {
            "product_id": product_id,
            "event_type": event_type,
            "event_name": EVENT_TYPES.get(event_type, "Không rõ"),
            "actor": session["user"],
            "timestamp": datetime.now().isoformat(),
            "details": {k: v for k, v in details.items() if v}, # Chỉ lưu các giá trị không rỗng
            "proofs": [] # Sẽ dùng để lưu link file bằng chứng
        }

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


# ════════════════════════════════════════════════════════════════
#  ADMIN — Dashboard, Validate, Tamper
# ════════════════════════════════════════════════════════════════
@app.route("/admin")
@login_required(role="admin")
def admin():
    all_blocks = [b.to_dict() for b in bc.get_all_blocks()]
    return render_template("admin.html", blocks=all_blocks)


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
    try:
        bc.tamper_block(index, "location", f"[TAMPERED] - Dữ liệu bị sửa lúc {datetime.now().strftime('%H:%M:%S')}")
        flash(f"⚠️ Đã tamper block #{index}. Chạy Validate để kiểm tra.", "warning")
    except ValueError as e:
        flash(f"Lỗi tamper: {e}", "danger")
    return redirect(url_for("admin"))


@app.route("/admin/reset_chain", methods=["POST"])
@login_required(role="admin")
def reset_chain():
    """Xóa chain trong database và tạo lại genesis block — dùng khi muốn demo từ đầu."""
    global bc
    try:
        # Gọi hàm reset mới trong lớp Blockchain để xóa collection trong DB
        bc.reset_chain_in_db()

        # Khởi tạo lại đối tượng blockchain để nạp lại genesis block mới vào bộ nhớ
        bc = Blockchain()

        flash("✅ Đã reset chain trong database về genesis block.", "success")
    except Exception as e:
        flash(f"❌ Có lỗi xảy ra khi reset chain: {e}", "danger")
    return redirect(url_for("admin"))


# ════════════════════════════════════════════════════════════════
#  QR SCAN — Để sau
# ════════════════════════════════════════════════════════════════
@app.route("/scan")
@login_required(role="consumer")
def scan():
    """
    ███████████████████████████████████████████████████████████████
    ██                                                           ██
    ██   TÍNH NĂNG QUÉT MÃ QR — CHƯA TRIỂN KHAI                  ██
    ██                                                           ██
    ██   Cần HTTPS để trình duyệt cho phép truy cập camera.      ██
    ██   Bước tiếp theo sau khi deploy lên Render.com:           ██
    ██                                                           ██
    ██   1. Thêm html5-qrcode vào templates/scan.html            ██
    ██   2. Dùng Html5QrcodeScanner để scan QR                   ██
    ██   3. Khi scan xong, redirect đến /trace?product_id=xxx    ██
    ██   4. Đổi make_qr_base64() để encode URL thay vì text      ██
    ██                                                           ██
    ███████████████████████████████████████████████████████████████
    """
    return render_template("scan_todo.html")


# ════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)