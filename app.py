from flask import Flask, render_template, request, redirect, url_for, send_file
import boto3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Định cấu hình thư mục cho các file được upload tạm thời
UPLOAD_FOLDER = '/tmp' # Sử dụng thư mục tạm thời
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Giới hạn 16MB cho file upload

# Khởi tạo client S3
# Boto3 sẽ tự động tìm kiếm thông tin xác thực từ IAM Role (khuyến nghị)
# hoặc biến môi trường, hoặc file ~/.aws/credentials
s3 = boto3.client('s3')

# Route chính: Liệt kê các Bucket và hiển thị form chọn Bucket
@app.route('/')
def index():
    try:
        response = s3.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        return render_template('index.html', buckets=buckets, current_bucket=None, objects=[], object_content=None)
    except Exception as e:
        return render_template('error.html', error=f"Lỗi khi liệt kê các bucket: {e}")

# Route để liệt kê các Object trong một Bucket đã chọn
@app.route('/bucket/<bucket_name>')
def list_objects(bucket_name):
    try:
        response = s3.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]

        objects_response = s3.list_objects_v2(Bucket=bucket_name)
        objects = []
        if 'Contents' in objects_response:
            objects = objects_response['Contents']
            # Chỉ lấy Key (tên file) và Size
            objects = [{'Key': obj['Key'], 'Size': obj['Size']} for obj in objects]

        return render_template('index.html',
                               buckets=buckets,
                               current_bucket=bucket_name,
                               objects=objects,
                               object_content=None,
                               # THÊM CÁC BIẾN NÀY VÀO ĐÂY:
                               object_content_type=None, # Khi liệt kê, không có nội dung cụ thể
                               is_text_file=None,        # Khi liệt kê, không xác định loại file cụ thể
                               current_object_key=None   # Khi liệt kê, không có object nào đang được xem
                               )
    except Exception as e:
        return render_template('error.html', error=f"Lỗi khi liệt kê các object trong bucket '{bucket_name}': {e}")
# Route để hiển thị nội dung của một Object
@app.route('/bucket/<bucket_name>/show/<path:object_key>')
def show_object_content(bucket_name, object_key):
    try:
        obj_metadata = s3.head_object(Bucket=bucket_name, Key=object_key) # Lấy metadata để có ContentType
        content_type = obj_metadata.get('ContentType', 'application/octet-stream')

        # Kiểm tra nếu là file văn bản
        if content_type.startswith(('text/', 'application/json', 'application/xml')) or \
           'charset' in content_type: # Các loại file text thường có charset
            obj = s3.get_object(Bucket=bucket_name, Key=object_key)
            content = obj['Body'].read(1024 * 1024 * 1).decode('utf-8', errors='ignore') # Đọc tối đa 1MB
            is_text_file = True
        elif content_type.startswith('image/'):
            # Đối với hình ảnh, chúng ta sẽ không đọc nội dung mà gửi URL về để hiển thị
            # Cần một URL công khai hoặc pre-signed URL.
            # Để đơn giản, ở đây ta sẽ chỉ cho phép download hoặc chuyển hướng người dùng đến URL của S3 object
            # (nếu bucket của bạn là public hoặc bạn tạo pre-signed URL)
            is_text_file = False
            content = None # Không đọc nội dung nhị phân
        else: # Các loại file khác (PDF, video, binary...)
            is_text_file = False
            content = None # Không đọc nội dung nhị phân
            
        response = s3.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        objects_response = s3.list_objects_v2(Bucket=bucket_name)
        objects = [{'Key': obj_item['Key'], 'Size': obj_item['Size']} for obj_item in objects_response.get('Contents', [])]

        return render_template('index.html', 
                               buckets=buckets, 
                               current_bucket=bucket_name, 
                               objects=objects, 
                               object_content=content, # Truyền nội dung (chỉ cho file text)
                               current_object_key=object_key,
                               is_text_file=is_text_file, # Biến flag để template biết là file text hay không
                               object_content_type=content_type # Truyền Content-Type
                               )
    except Exception as e:
        return render_template('error.html', error=f"Lỗi khi hiển thị nội dung object '{object_key}': {e}")
    
# Route để Download một Object
@app.route('/bucket/<bucket_name>/download/<path:object_key>')
def download_object(bucket_name, object_key):
    try:
        file_obj = s3.get_object(Bucket=bucket_name, Key=object_key)
        
        # Tạo một file tạm thời để lưu nội dung trước khi gửi
        temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(os.path.basename(object_key)))
        with open(temp_file_path, 'wb') as f:
            f.write(file_obj['Body'].read())
        
        return send_file(temp_file_path, as_attachment=True, download_name=os.path.basename(object_key))
    except Exception as e:
        return render_template('error.html', error=f"Lỗi khi download object '{object_key}': {e}")
    finally:
        # Xóa file tạm thời sau khi gửi đi (đảm bảo an toàn)
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# Route để Upload một Object mới
@app.route('/bucket/<bucket_name>/upload', methods=['POST'])
def upload_object(bucket_name):
    try:
        if 'file' not in request.files:
            return redirect(url_for('list_objects', bucket_name=bucket_name))
        
        file = request.files['file']
        if file.filename == '':
            return redirect(url_for('list_objects', bucket_name=bucket_name))
        
        if file:
            filename = secure_filename(file.filename)
            s3.upload_fileobj(file, bucket_name, filename)
            return redirect(url_for('list_objects', bucket_name=bucket_name))
    except Exception as e:
        return render_template('error.html', error=f"Lỗi khi upload file lên bucket '{bucket_name}': {e}")

# Route lỗi chung (nếu bạn muốn hiển thị lỗi một cách đẹp hơn)
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == '__main__':
    # Lưu ý: Không nên chạy app.run() trực tiếp trong production.
    # Gunicorn sẽ quản lý việc chạy Flask app.
    app.run(debug=True, host='0.0.0.0', port=5000)