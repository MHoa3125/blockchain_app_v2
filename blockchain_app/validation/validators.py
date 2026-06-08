# validation/validators.py
# ────────────────────────────────────────────────────────────────
from abc import ABC, abstractmethod
from datetime import datetime
import re
from .result import ValidationResult
from .rules import MIN_ALTITUDE, MAX_ALTITUDE, VALID_REGIONS, VALID_COFFEE_VARIETIES
from blockchain_app.blockchain import Blockchain
bc = Blockchain()

def get_latest_block_from_db(product_id: str):
    if not product_id:
        return None
    doc = bc.collection.find_one({"data.product_id": product_id}, sort=[("index", -1)])
    return bc._from_doc(doc) if doc else None

class IValidator(ABC):
    @abstractmethod
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        """
        Xác thực logic nghiệp vụ cho dữ liệu của một sự kiện.
        :param data: Dữ liệu sự kiện cần kiểm tra (chứa chi tiết details, event_type,...)
        :param files: File upload đính kèm (chứa chứng nhận/minh chứng)
        :return: Đối tượng ValidationResult
        """
        pass

class HarvestValidator(IValidator):
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        result = ValidationResult()
        details = data.get("details", {})
        print(f"📝 [Validator] Details from form: {details}")
        
        # 1. Kiểm tra các trường bắt buộc trên Form
        required_fields = {
            "farm_name": "Tên nông trại",
            "coffee_variety": "Giống cà phê",
            "region": "Khu vực",
            "altitude": "Độ cao",
            "planting_date": "Ngày trồng",
            "harvest_date": "Ngày thu hoạch"
        }
        
        for field, label in required_fields.items():
            if not details.get(field):
                result.add_error(f"Lỗi Logic: Trường '{label}' không được để trống.")
                
        # Nếu thiếu trường bắt buộc, trả về kết quả lỗi ngay
        if not result.is_valid:
            return result

        # 2. Xác thực Độ cao (Altitude)
        altitude_str = str(details.get("altitude", ""))
        match = re.search(r"\d+", altitude_str)
        if match:
            try:
                altitude = int(match.group())
                if altitude < MIN_ALTITUDE or altitude > MAX_ALTITUDE:
                    result.add_error(f"Lỗi Logic: Độ cao {altitude}m nằm ngoài khoảng cho phép ({MIN_ALTITUDE}m - {MAX_ALTITUDE}m).")
            except ValueError:
                result.add_error("Lỗi Logic: Độ cao canh tác phải là giá trị số.")
        else:
            result.add_error("Lỗi Logic: Không tìm thấy giá trị số hợp lệ cho độ cao.")

        # 3. Xác thực các quy tắc Thời gian (Dates)
        planting_date_str = details.get("planting_date", "")
        harvest_date_str = details.get("harvest_date", "")
        
        try:
            planting_date = datetime.strptime(planting_date_str, "%Y-%m-%d")
            harvest_date = datetime.strptime(harvest_date_str, "%Y-%m-%d")
            current_date = datetime.now()

            # Ngày thu hoạch không được lớn hơn ngày hiện tại
            if harvest_date > current_date:
                result.add_error("Lỗi Logic: Ngày thu hoạch không được lớn hơn ngày hiện tại.")

            # Ngày thu hoạch phải sau ngày trồng
            if harvest_date <= planting_date:
                result.add_error("Lỗi Logic: Ngày thu hoạch phải diễn ra sau ngày trồng.")
        except ValueError:
            result.add_error("Lỗi Logic: Định dạng ngày trồng hoặc ngày thu hoạch không hợp lệ (yêu cầu YYYY-MM-DD).")

        # 4. Xác thực giống cà phê (Variety) - Mức độ cảnh báo (Warning)
        variety = details.get("coffee_variety", "")
        if not any(valid_var in variety.lower() for valid_var in VALID_COFFEE_VARIETIES):
            result.add_warning(f"Cảnh báo: Giống cà phê '{variety}' có thể không thuộc các giống Arabica khuyến nghị.")

        # 5. Xác thực khu vực trồng (Region) - Mức độ cảnh báo (Warning)
        region = details.get("region", "")
        if not any(valid_reg in region.lower() for valid_reg in VALID_REGIONS):
            result.add_warning(f"Cảnh báo: Vùng trồng '{region}' có thể nằm ngoài ranh giới vùng Cầu Đất được định nghĩa.")

        # 6. Xác thực Chứng nhận / Tài liệu minh chứng (OCR Simulation / Real Text Parsing / API OCR)
        has_file = False
        if files and 'proof_file' in files:
            file = files['proof_file']
            if file and file.filename != '':
                has_file = True
                filename = file.filename.lower()
                cert_data = None
                
                # A. Nếu là file text (.txt), tiến hành đọc và phân tích nội dung thực tế (Real Text Parser)
                if filename.endswith('.txt'):
                    try:
                        content = file.read().decode('utf-8')
                        file.seek(0)  # Reset con trỏ file
                        cert_data = self._parse_certificate_text(content)
                        print(f"📄 [TXT Reader] File: {filename}")
                        print(f"📄 parsed cert_data: {cert_data}")
                    except Exception as e:
                        result.add_error(f"Lỗi Hệ Thống: Không thể đọc tệp văn bản: {e}")
                        return result
                
                # B. Nếu là file ảnh (png, jpg, jpeg), thử gửi đến OCR API trực tuyến miễn phí (OCR.space)
                elif filename.endswith(('.png', '.jpg', '.jpeg')):
                    extracted_text = self._ocr_via_api(file, file.filename)
                    if extracted_text:
                        print(f"🔍 [OCR.space API] Đọc được chữ trong ảnh:\n{extracted_text}")
                        cert_data = self._parse_certificate_text(extracted_text)
                    else:
                        print("⚠️ [OCR API thất bại hoặc quá hạn] Chuyển sang cơ chế giả lập qua tên file.")
                
                # C. Nếu không có dữ liệu trích xuất từ các bước trên, chuyển sang giả lập dựa trên tên file (Mock OCR)
                if not cert_data:
                    mock_db = {
                        "hoamai": {
                            "certificate_id": "VG-CD-2025-0001",
                            "farm_name": "Nông trại Hoa Mai",
                            "coffee_variety": "Arabica",
                            "issue_date": "2025-01-01",
                            "expiry_date": "2027-01-01",
                            "issuing_authority": "VietGAP Authority"
                        },
                        "hoalan": {
                            "certificate_id": "VG-CD-2025-0002",
                            "farm_name": "Nông trại Hoa Lan",
                            "coffee_variety": "Arabica",
                            "issue_date": "2025-02-15",
                            "expiry_date": "2027-02-15",
                            "issuing_authority": "VietGAP Authority"
                        },
                        "expired": {
                            "certificate_id": "VG-CD-2022-0003",
                            "farm_name": "Nông trại Hoa Mai",
                            "coffee_variety": "Arabica",
                            "issue_date": "2022-01-01",
                            "expiry_date": "2024-01-01",
                            "issuing_authority": "VietGAP Authority"
                        },
                        "invalid_id": {
                            "certificate_id": "INVALID-ID-123",
                            "farm_name": "Nông trại Hoa Mai",
                            "coffee_variety": "Arabica",
                            "issue_date": "2025-01-01",
                            "expiry_date": "2027-01-01",
                            "issuing_authority": "VietGAP Authority"
                        }
                    }
                    for key, data in mock_db.items():
                        if key in filename:
                            cert_data = data
                            break
                
                if cert_data:
                    # Kiểm tra sự tồn tại của các trường thông tin bắt buộc
                    required_cert_fields = ["certificate_id", "farm_name", "coffee_variety", "issue_date", "expiry_date", "issuing_authority"]
                    missing_fields = []
                    for f_field in required_cert_fields:
                        if not cert_data.get(f_field):
                            missing_fields.append(f_field)
                    
                    if missing_fields:
                        result.add_error(f"Lỗi OCR: Tài liệu trích xuất thiếu các trường bắt buộc: {', '.join(missing_fields)}")
                    
                    # Chỉ kiểm tra logic khi đủ các trường bắt buộc
                    if not missing_fields:
                        # B. Kiểm tra định dạng của mã chứng nhận (Hỗ trợ VG-CD-YYYY-XXXX hoặc VG 01-2023-CF / TCCS)
                        cert_id = cert_data.get("certificate_id", "").strip()
                        if not re.match(r"^[A-Z0-9 \-\.\/]+$", cert_id, re.IGNORECASE) or "VG" not in cert_id.upper():
                            result.add_error(f"Lỗi Chứng nhận: Mã chứng nhận '{cert_id}' không đúng định dạng chuẩn (phải bắt đầu hoặc chứa ký hiệu VG).")
                        
                        # C. Kiểm tra ngày hiệu lực và ngày hết hạn
                        try:
                            issue_date = datetime.strptime(cert_data.get("issue_date", ""), "%Y-%m-%d")
                            expiry_date = datetime.strptime(cert_data.get("expiry_date", ""), "%Y-%m-%d")
                            current_date = datetime.now()
                            harvest_date_str = details.get("harvest_date", "")
                            harvest_date = datetime.strptime(harvest_date_str, "%Y-%m-%d") if harvest_date_str else current_date
                            
                            if issue_date > current_date:
                                result.add_error(f"Lỗi Chứng nhận: Ngày cấp '{cert_data.get('issue_date')}' không được ở tương lai.")
                            if expiry_date <= issue_date:
                                result.add_error("Lỗi Chứng nhận: Ngày hết hạn phải sau ngày cấp.")
                            if expiry_date < harvest_date:
                                result.add_error(f"Lỗi Chứng nhận: Chứng nhận đã hết hạn vào ngày '{cert_data.get('expiry_date')}' trước thời điểm thu hoạch.")
                        except (ValueError, TypeError):
                            result.add_error("Lỗi Chứng nhận: Ngày cấp hoặc ngày hết hạn trên chứng nhận không đúng định dạng YYYY-MM-DD.")
                        
                        # D. Kiểm tra tính nhất quán giữa dữ liệu trên chứng nhận và dữ liệu do người dùng khai báo
                        form_farm = details.get("farm_name", "")
                        form_variety = details.get("coffee_variety", "")
                        
                        cert_farm = cert_data.get("farm_name", "")
                        cert_variety = cert_data.get("coffee_variety", "")
                        
                        if cert_farm.lower() != form_farm.lower():
                            result.add_error(f"Lỗi Chứng nhận: Tên nông trại trên form ('{form_farm}') không khớp với thông tin trên chứng nhận ('{cert_farm}').")
                        if cert_variety.lower() not in form_variety.lower() and form_variety.lower() not in cert_variety.lower():
                            result.add_error(f"Lỗi Chứng nhận: Giống cà phê trên form ('{form_variety}') không khớp với thông tin trên chứng nhận ('{cert_variety}').")
                else:
                    result.add_warning("Cảnh báo OCR: Không thể trích xuất tự động thông tin từ tài liệu tải lên. Vui lòng đặt tên tệp chứa từ khóa mẫu như 'hoamai' hoặc 'hoalan' để hệ thống tự động đối chiếu.")
        
        if not has_file:
            result.add_error("Lỗi Chứng nhận: Tài liệu minh chứng bắt buộc phải được tải lên.")

        return result

    def _parse_certificate_text(self, content: str) -> dict:
        cert_data = {}
        content_lower = content.lower()

        # 1. Trích xuất Certificate ID (Số/Số hiệu: VG 01-2023-CF / TCCS)
        id_match = re.search(r"(?:certificate\s*id|số|số\s*hiệu):\s*([A-Z0-9 \-\.\/]+)", content, re.IGNORECASE)
        if id_match:
            cert_data["certificate_id"] = id_match.group(1).strip()

        # 2. Trích xuất Farm Name (Tìm các tên nông trại đăng ký sẵn trong hệ thống)
        known_farms = [
            "Nông trại Hoa Mai",
            "Nông trại Hoa Lan",
            "Trang trại Cầu Đất",
            "Trang trại Phúc Lâm",
            "Green Farm Cầu Đất"
        ]
        for farm in known_farms:
            if farm.lower() in content_lower:
                cert_data["farm_name"] = farm
                break
        
        if "farm_name" not in cert_data:
            farm_match = re.search(r"farm\s*name:\s*([^\r\n]+)", content, re.IGNORECASE)
            if farm_match:
                cert_data["farm_name"] = farm_match.group(1).strip()

        # 3. Trích xuất Coffee Variety (Giống cà phê)
        known_varieties = ["Arabica", "Robusta", "Cát Nghiên", "Typica", "Bourbon"]
        for var in known_varieties:
            if var.lower() in content_lower:
                cert_data["coffee_variety"] = var
                break
        
        if "coffee_variety" not in cert_data:
            variety_match = re.search(r"coffee\s*variety:\s*([^\r\n]+)", content, re.IGNORECASE)
            if variety_match:
                cert_data["coffee_variety"] = variety_match.group(1).strip()

        # 4. Trích xuất Issue Date (Ngày cấp: 15 tháng 10 năm 2023 hoặc 15/10/2023)
        issue_match_vn = re.search(r"(?:ngày\s*cấp|ngày|cấp\s*ngày|issue\s*date):?\s*(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", content, re.IGNORECASE)
        if issue_match_vn:
            day, month, year = issue_match_vn.groups()
            cert_data["issue_date"] = f"{year}-{int(month):02d}-{int(day):02d}"
        else:
            issue_match_std = re.search(r"(?:ngày\s*cấp|ngày|cấp\s*ngày|issue\s*date):?\s*(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", content, re.IGNORECASE)
            if issue_match_std:
                year, month, day = issue_match_std.groups()
                cert_data["issue_date"] = f"{year}-{int(month):02d}-{int(day):02d}"
            else:
                issue_match_vn_slash = re.search(r"(?:ngày\s*cấp|ngày|cấp\s*ngày|issue\s*date):?\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", content, re.IGNORECASE)
                if issue_match_vn_slash:
                    day, month, year = issue_match_vn_slash.groups()
                    cert_data["issue_date"] = f"{year}-{int(month):02d}-{int(day):02d}"

        # 5. Trích xuất Expiry Date (Có giá trị đến: 14 tháng 10 năm 2026 hoặc 14/10/2026)
        expiry_match_vn = re.search(r"(?:có\s*giá\s*trị\s*đến|ngày\s*hết\s*hạn|hết\s*hạn|giá\s*trị\s*đến|expiry\s*date):?\s*(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", content, re.IGNORECASE)
        if expiry_match_vn:
            day, month, year = expiry_match_vn.groups()
            cert_data["expiry_date"] = f"{year}-{int(month):02d}-{int(day):02d}"
        else:
            expiry_match_std = re.search(r"(?:có\s*giá\s*trị\s*đến|ngày\s*hết\s*hạn|hết\s*hạn|giá\s*trị\s*đến|expiry\s*date):?\s*(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", content, re.IGNORECASE)
            if expiry_match_std:
                year, month, day = expiry_match_std.groups()
                cert_data["expiry_date"] = f"{year}-{int(month):02d}-{int(day):02d}"
            else:
                expiry_match_vn_slash = re.search(r"(?:có\s*giá\s*trị\s*đến|ngày\s*hết\s*hạn|hết\s*hạn|giá\s*trị\s*đến|expiry\s*date):?\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", content, re.IGNORECASE)
                if expiry_match_vn_slash:
                    day, month, year = expiry_match_vn_slash.groups()
                    cert_data["expiry_date"] = f"{year}-{int(month):02d}-{int(day):02d}"

        # 6. Trích xuất Issuing Authority (Tổ chức cấp - sử dụng từ khóa linh hoạt chống sai số OCR)
        if any(kw in content_lower for kw in ["nông lâm", "thủy sản", "thuy san", "kiểm định", "kiếm định", "chất lượng"]):
            cert_data["issuing_authority"] = "Trung tâm kiểm định và chứng nhận chất lượng nông lâm thủy sản"
        elif any(kw in content_lower for kw in ["nông thôn", "phát triển nông", "sở nông"]):
            cert_data["issuing_authority"] = "Sở Nông nghiệp và Phát triển nông thôn"
        elif "vietgap" in content_lower:
            cert_data["issuing_authority"] = "VietGAP Authority"
        
        if "issuing_authority" not in cert_data:
            auth_match = re.search(r"issuing\s*authority:\s*([^\r\n]+)", content, re.IGNORECASE)
            if auth_match:
                cert_data["issuing_authority"] = auth_match.group(1).strip()

        return cert_data

    def _ocr_via_api(self, file_stream, filename: str) -> str:
        import requests
        try:
            url = "https://api.ocr.space/parse/image"
            file_stream.seek(0)
            file_bytes = file_stream.read()
            file_stream.seek(0)
            
            payload = {
                "apikey": "helloworld",
                "language": "auto",
                "OCREngine": "2",
                "isOverlayRequired": "false"
            }
            files_payload = {
                "file": (filename, file_bytes)
            }
            # Tăng timeout lên 15 giây để xử lý ảnh quét lớn hoặc khi kết nối mạng chậm
            response = requests.post(url, data=payload, files=files_payload, timeout=15)
            result = response.json()
            
            if result.get("OCRExitCode") == 1:
                parsed_results = result.get("ParsedResults", [])
                if parsed_results:
                    return parsed_results[0].get("ParsedText", "")
            else:
                err_msg = result.get("ErrorMessage", "")
                print(f"⚠️ OCR.space API Error: {err_msg}")
            return None
        except Exception as e:
            print(f"⚠️ Lỗi kết nối OCR API: {e}")
            return None

class NullValidator(IValidator):
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        # Đối tượng Null Object luôn trả về kết quả hợp lệ cho các event chưa có rule cụ thể
        return ValidationResult()


class ProcessingValidator(IValidator):
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        result = ValidationResult()
        details = data.get("details", {})
        product_id = data.get("product_id")
        
        # 1. Kiểm tra các trường bắt buộc trên Form
        required_fields = {
            "processing_method": "Phương pháp sơ chế",
            "processing_date": "Ngày sơ chế"
        }
        
        for field, label in required_fields.items():
            if not details.get(field):
                result.add_error(f"Lỗi Logic: Trường '{label}' không được để trống.")
                
        if not result.is_valid:
            return result

        # 2. Xác thực các quy tắc Thời gian (Dates)
        processing_date_str = details.get("processing_date", "")
        try:
            processing_date = datetime.strptime(processing_date_str, "%Y-%m-%d")
            current_date = datetime.now()

            # Ngày sơ chế không được lớn hơn ngày hiện tại
            if processing_date > current_date:
                result.add_error("Lỗi Logic: Ngày sơ chế không được lớn hơn ngày hiện tại.")

            # Kiểm tra thứ tự thời gian so với block thu hoạch trước đó
            if product_id:
                last_block = get_latest_block_from_db(product_id)
                if last_block and last_block.data.get("event_type") == "HARVEST":
                    harvest_date_str = last_block.data.get("details", {}).get("harvest_date", "")
                    if harvest_date_str:
                        harvest_date = datetime.strptime(harvest_date_str, "%Y-%m-%d")
                        if processing_date < harvest_date:
                            result.add_error("Lỗi Logic: Ngày sơ chế không được trước ngày thu hoạch.")
        except ValueError:
            result.add_error("Lỗi Logic: Định dạng ngày sơ chế không hợp lệ (yêu cầu YYYY-MM-DD).")

        # 3. Xác thực Thời gian lên men (Fermentation time)
        fermentation_str = details.get("fermentation_time_hours")
        if fermentation_str:
            try:
                fermentation_time = float(fermentation_str)
                if fermentation_time < 0:
                    result.add_error("Lỗi Logic: Thời gian lên men không được là số âm.")
                elif fermentation_time > 120:
                    result.add_warning("Cảnh báo: Thời gian lên men quá lâu (> 120 giờ) có thể làm giảm chất lượng hạt cà phê nhân.")
            except ValueError:
                result.add_error("Lỗi Logic: Thời gian lên men phải là giá trị số.")

        # 4. Xác thực Độ ẩm (Moisture percentage)
        moisture_str = details.get("moisture_percentage")
        if moisture_str:
            try:
                moisture = float(moisture_str)
                if moisture < 0 or moisture > 100:
                    result.add_error("Lỗi Logic: Độ ẩm (%) phải nằm trong khoảng từ 0% đến 100%.")
                elif moisture < 9.0 or moisture > 13.0:
                    result.add_warning(f"Cảnh báo: Độ ẩm tiêu chuẩn cho hạt cà phê nhân thường từ 9% đến 13%. Độ ẩm hiện tại ({moisture}%) nằm ngoài khoảng khuyến nghị.")
            except ValueError:
                result.add_error("Lỗi Logic: Độ ẩm phải là giá trị số.")

        return result


class RoastingValidator(IValidator):
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        result = ValidationResult()
        details = data.get("details", {})
        product_id = data.get("product_id")
        
        # 1. Kiểm tra các trường bắt buộc trên Form
        required_fields = {
            "roastery_name": "Tên xưởng rang",
            "roast_level": "Mức độ rang",
            "roast_date": "Ngày rang",
            "packaging_date": "Ngày đóng gói"
        }
        
        for field, label in required_fields.items():
            if not details.get(field):
                result.add_error(f"Lỗi Logic: Trường '{label}' không được để trống.")
                
        if not result.is_valid:
            return result

        # 2. Xác thực các quy tắc Thời gian (Dates)
        roast_date_str = details.get("roast_date", "")
        packaging_date_str = details.get("packaging_date", "")
        try:
            roast_date = datetime.strptime(roast_date_str, "%Y-%m-%d")
            packaging_date = datetime.strptime(packaging_date_str, "%Y-%m-%d")
            current_date = datetime.now()

            # Ngày không được lớn hơn ngày hiện tại
            if roast_date > current_date:
                result.add_error("Lỗi Logic: Ngày rang không được lớn hơn ngày hiện tại.")
            if packaging_date > current_date:
                result.add_error("Lỗi Logic: Ngày đóng gói không được lớn hơn ngày hiện tại.")

            # Ngày đóng gói phải sau hoặc bằng ngày rang
            if packaging_date < roast_date:
                result.add_error("Lỗi Logic: Ngày đóng gói phải diễn ra cùng ngày hoặc sau ngày rang.")

            # Kiểm tra thứ tự thời gian so với block sơ chế trước đó
            if product_id:
                last_block = get_latest_block_from_db(product_id)
                if last_block and last_block.data.get("event_type") == "PROCESSING":
                    processing_date_str = last_block.data.get("details", {}).get("processing_date", "")
                    if processing_date_str:
                        processing_date = datetime.strptime(processing_date_str, "%Y-%m-%d")
                        if roast_date < processing_date:
                            result.add_error("Lỗi Logic: Ngày rang không được trước ngày sơ chế.")
        except ValueError:
            result.add_error("Lỗi Logic: Định dạng ngày rang hoặc ngày đóng gói không hợp lệ (yêu cầu YYYY-MM-DD).")

        # 3. Xác thực Nhiệt độ rang (Roast temperature)
        temp_str = details.get("roast_temperature_celsius")
        if temp_str:
            try:
                temp = float(temp_str)
                if temp < 0:
                    result.add_error("Lỗi Logic: Nhiệt độ rang không được là số âm.")
                elif temp < 150.0 or temp > 250.0:
                    result.add_warning(f"Cảnh báo: Nhiệt độ rang khuyến nghị thường từ 150°C đến 250°C. Nhiệt độ hiện tại ({temp}°C) nằm ngoài khoảng tối ưu.")
            except ValueError:
                result.add_error("Lỗi Logic: Nhiệt độ rang phải là giá trị số.")

        return result


class DistributionValidator(IValidator):
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        result = ValidationResult()
        details = data.get("details", {})
        product_id = data.get("product_id")
        
        # 1. Kiểm tra các trường bắt buộc trên Form
        required_fields = {
            "shipment_id": "Mã lô hàng vận chuyển",
            "delivery_date": "Ngày giao hàng"
        }
        
        for field, label in required_fields.items():
            if not details.get(field):
                result.add_error(f"Lỗi Logic: Trường '{label}' không được để trống.")
                
        if not result.is_valid:
            return result

        # 2. Xác thực các quy tắc Thời gian (Dates)
        delivery_date_str = details.get("delivery_date", "")
        try:
            delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d")
            current_date = datetime.now()

            # Ngày giao hàng không được lớn hơn ngày hiện tại
            if delivery_date > current_date:
                result.add_error("Lỗi Logic: Ngày giao hàng không được lớn hơn ngày hiện tại.")

            # Kiểm tra thứ tự thời gian so với block rang xay trước đó
            if product_id:
                last_block = get_latest_block_from_db(product_id)
                if last_block and last_block.data.get("event_type") == "ROASTING":
                    packaging_date_str = last_block.data.get("details", {}).get("packaging_date", "")
                    if packaging_date_str:
                        packaging_date = datetime.strptime(packaging_date_str, "%Y-%m-%d")
                        if delivery_date < packaging_date:
                            result.add_error("Lỗi Logic: Ngày giao hàng không được trước ngày đóng gói của xưởng rang.")
        except ValueError:
            result.add_error("Lỗi Logic: Định dạng ngày giao hàng không hợp lệ (yêu cầu YYYY-MM-DD).")

        return result


class RetailValidator(IValidator):
    def validate(self, data: dict, files: dict = None) -> ValidationResult:
        result = ValidationResult()
        details = data.get("details", {})
        product_id = data.get("product_id")
        
        # 1. Kiểm tra các trường bắt buộc trên Form
        required_fields = {
            "shop_name": "Tên quán cà phê",
            "receive_date": "Ngày nhận hàng"
        }
        
        for field, label in required_fields.items():
            if not details.get(field):
                result.add_error(f"Lỗi Logic: Trường '{label}' không được để trống.")
                
        if not result.is_valid:
            return result

        # 2. Xác thực các quy tắc Thời gian (Dates)
        receive_date_str = details.get("receive_date", "")
        try:
            receive_date = datetime.strptime(receive_date_str, "%Y-%m-%d")
            current_date = datetime.now()

            # Ngày nhận hàng không được lớn hơn ngày hiện tại
            if receive_date > current_date:
                result.add_error("Lỗi Logic: Ngày nhận hàng không được lớn hơn ngày hiện tại.")

            # Kiểm tra thứ tự thời gian so với block vận chuyển trước đó
            if product_id:
                last_block = get_latest_block_from_db(product_id)
                if last_block and last_block.data.get("event_type") == "DISTRIBUTION":
                    delivery_date_str = last_block.data.get("details", {}).get("delivery_date", "")
                    if delivery_date_str:
                        delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d")
                        if receive_date < delivery_date:
                            result.add_error("Lỗi Logic: Ngày nhận hàng không được trước ngày giao hàng của nhà phân phối.")
        except ValueError:
            result.add_error("Lỗi Logic: Định dạng ngày nhận hàng không hợp lệ (yêu cầu YYYY-MM-DD).")

        return result
