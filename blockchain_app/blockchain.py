import hashlib
import json
from datetime import datetime
from pymongo import MongoClient, ASCENDING
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Cấu hình MongoDB ---
MONGO_URI = "mongodb+srv://tranthimyhoa3125_db_user:Admin123@mycluster.22hhxtr.mongodb.net/?appName=MyCluster"
DB_NAME = "blockchain_db"
COLLECTION_NAME = "chain"
# -------------------------

class Block:
    
    def __init__(self, index, timestamp, data, previous_hash, hash_value=None):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        # Nếu load từ DB → dùng hash cũ, nếu tạo block mới → tính hash mới
        self.hash = hash_value if hash_value else self.calculate_hash()

    @property
    def product_id(self):
        """Helper để truy cập nhanh product_id từ trong data."""
        return self.data.get("product_id")

    def calculate_hash(self):
        """
        Hash = SHA256 của các field cố định + toàn bộ dict data.
        sort_keys=True đảm bảo cùng dữ liệu → cùng hash.
        """
        block_content = {
            "index":         self.index,
            "timestamp":     self.timestamp,
            "data":          self.data,
            "previous_hash": self.previous_hash,
        }
        # Dumps với sort_keys=True để đảm bảo hash nhất quán
        block_string = json.dumps(block_content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(block_string.encode("utf-8")).hexdigest()

    def to_dict(self):
        """Lưu block với cấu trúc lồng nhau, nhất quán với calculate_hash."""
        return {
            "index":         self.index,
            "timestamp":     self.timestamp,
            "data":          self.data,
            "previous_hash": self.previous_hash,
            "hash":          self.hash,
        }

class Blockchain:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self.chain = []
        self._init_db_connection()
        self._load_chain_from_db()
        if not self.chain:
            self._create_genesis_block()

    def _init_db_connection(self):
        """Khởi tạo kết nối đến MongoDB và lấy collection."""
        try:
            self.client = MongoClient(MONGO_URI)
            self.db = self.client[DB_NAME]
            self.collection = self.db[COLLECTION_NAME]
            self.collection.create_index([("index", ASCENDING)], unique=True)
            print("✅ Kết nối MongoDB thành công.")
        except Exception as e:
            print(f"❌ Lỗi kết nối MongoDB: {e}")
            raise

    def _write_to_google_sheet(self, block):
        try:
            print("📝 Đang ghi vào Google Sheet...")
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive"
            ]
            BASE_DIR = os.path.dirname(__file__)
            creds_path = os.path.join(BASE_DIR,"credentials.json")
            if os.getenv("GOOGLE_CREDENTIALS"):
                content = os.getenv("GOOGLE_CREDENTIALS")
                with open(creds_path,"w") as f:
                    f.write(content)
                print("✅ credentials file created")
            
            # Kiểm tra xem file credentials.json có tồn tại trước khi đọc
            if not os.path.exists(creds_path):
                print("⚠️ Cảnh báo: Không tìm thấy file 'credentials.json'. Bỏ qua đồng bộ Google Sheet khi chạy cục bộ.")
                return

            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
            client = gspread.authorize(creds)
            sheet = client.open("Blockchain Log").sheet1
            data_str = json.dumps(block.data, ensure_ascii=False)
            row = [
                block.index,
                block.timestamp,
                data_str,
                block.previous_hash,
                block.hash
            ]
            sheet.append_row(row)
            print("✅ Ghi vào Google Sheet thành công.")
        except Exception as e:
            print(f"❌ Lỗi khi ghi vào Google Sheet: {e}")

    def _from_doc(self, doc: dict) -> Block:
        """Helper để chuyển đổi document từ MongoDB thành đối tượng Block."""
        return Block(
            index=doc["index"],
            timestamp=doc["timestamp"],
            data=doc["data"],
            previous_hash=doc["previous_hash"],
            hash_value=doc["hash"]
        )

    def _load_chain_from_db(self):
        """Tải toàn bộ chain từ MongoDB."""
        try:
            chain_data = self.collection.find().sort("index", ASCENDING)
            self.chain = [self._from_doc(b) for b in chain_data]
            print(f"📚 Đã tải {len(self.chain)} block từ database.")
        except Exception as e:
            print(f"❌ Lỗi khi tải chain từ DB: {e}")
            self.chain = []

    def _create_genesis_block(self):
        genesis_data = {
            "product_id": "GENESIS",
            "event": "Genesis",
            "actor": "system",
            "product_name": "Genesis Block",
        }
        genesis = Block(
            index=0,
            timestamp="2026-01-01 00:00:00",
            data=genesis_data,
            previous_hash="0" * 64,
        )
        self.chain.append(genesis)
        # Chỉ chèn nếu collection trống
        if self.collection.count_documents({}) == 0:
            self.collection.insert_one(genesis.to_dict())

    # ── Thêm block mới (Proof of Authority) ──────────────────
    def add_block(self, data: dict, actor_sub_role: str):
        """
        Thêm block mới vào chain với cơ chế đồng thuận Proof of Authority (PoA) linh hoạt.
        Quyền được xác thực bằng cách so sánh vai trò của người dùng (truyền từ app.py)
        với vai trò yêu cầu của sự kiện.
        """
        actor = data.get("actor")
        event_type = data.get("event_type")
        product_id = data.get("product_id")

        # 1. KIỂM TRA QUYỀN (AUTHORITY CHECK)
        role_for_event = next((role for role, event in [
            ("farmer", "HARVEST"), ("processor", "PROCESSING"),
            ("roaster", "ROASTING"), ("distributor", "DISTRIBUTION"),
            ("retailer", "RETAIL")
        ] if event == event_type), None)

        if not role_for_event:
            raise ValueError(f"Loại sự kiện '{event_type}' không hợp lệ.")

        # So sánh vai trò của người dùng với vai trò yêu cầu của sự kiện
        if actor_sub_role != role_for_event:
            raise ValueError(
                f"Vai trò '{actor_sub_role}' của người dùng '{actor}' không có quyền thực hiện hành động '{event_type}' (yêu cầu vai trò '{role_for_event}')."
            )

        # 2. KIỂM TRA LOGIC NGHIỆP VỤ
        is_genesis_event = (event_type == "HARVEST")
        if not product_id:
            raise ValueError("Product ID là bắt buộc.")

        if is_genesis_event:
            if self.get_trace(product_id):
                raise ValueError(f"Product ID '{product_id}' đã tồn tại.")
        else:
            if not self.get_trace(product_id):
                raise ValueError(f"Product ID '{product_id}' chưa tồn tại.")

        # 3. TẠO VÀ THÊM BLOCK MỚI
        new_block = Block(
            index=len(self.chain),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data=data,
            previous_hash=self.chain[-1].hash,
        )
        self.chain.append(new_block)
        self.collection.insert_one(new_block.to_dict())
        self._write_to_google_sheet(new_block)
        return new_block

    # ── Các hàm truy vấn ──────────────────────────────────────────
    def get_trace(self, product_id: str) -> list['Block']:
        """Lấy tất cả các block liên quan đến một product_id, sắp xếp theo thời gian."""
        return sorted(
            [b for b in self.chain if b.data.get("product_id") == product_id],
            key=lambda b: b.timestamp
        )

    def get_last_block(self, product_id: str) -> 'Block' or None:
        """Lấy block cuối cùng (mới nhất) của một sản phẩm."""
        trace = self.get_trace(product_id)
        return trace[-1] if trace else None

    def get_all_product_ids(self) -> list[str]:
        """
        Lấy danh sách tất cả các product_id duy nhất từ database,
        loại trừ 'GENESIS'.
        """
        try:
            product_ids = self.collection.distinct("data.product_id")
            return [pid for pid in product_ids if pid != 'GENESIS']
        except Exception as e:
            print(f"❌ Lỗi khi lấy danh sách product_id: {e}")
            return []

    def get_products_by_actor(self, actor_name: str) -> list[str]:
        """
        Lấy danh sách các product_id duy nhất mà một actor đã tham gia,
        loại trừ 'GENESIS'.
        """
        try:
            # Sử dụng query để lọc theo tên actor
            query = {"data.actor": actor_name}
            product_ids = self.collection.distinct("data.product_id", query)
            return [pid for pid in product_ids if pid != 'GENESIS']
        except Exception as e:
            print(f"❌ Lỗi khi lấy danh sách sản phẩm theo actor '{actor_name}': {e}")
            return []

    def get_blocks_by_event(self, event_type: str) -> list:
        """Lấy tất cả các block có một loại sự kiện cụ thể trực tiếp từ DB."""
        # Chỉ cần trả về list các document để app.py có thể dùng len()
        blocks_cursor = self.collection.find({"data.event_type": event_type})
        return list(blocks_cursor)

    def delete_all_blocks(self):
        """Xóa tất cả các block và tạo lại genesis block."""
        try:
            self.collection.delete_many({})
            self.chain = []
            self._create_genesis_block()
            print("✅ Đã xóa toàn bộ chain và tạo lại genesis block.")
            return True
        except Exception as e:
            print(f"❌ Lỗi khi xóa chain: {e}")
            return False