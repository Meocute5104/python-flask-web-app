from flask import Flask, render_template, request, redirect, url_for
import boto3
import os
import uuid # Để tạo ID duy nhất cho item DynamoDB và tên file S3

app = Flask(__name__)

# Cấu hình AWS SDK
# Boto3 sẽ tự động lấy credentials từ IAM Role của EC2 Instance
# nếu được gắn đúng cách. Không cần Access Key/Secret Key ở đây.
s3_client = boto3.client('s3', region_name=os.environ.get('AWS_REGION', 'ap-southeast-1'))
dynamodb_client = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'ap-southeast-1'))

# Đặt tên Bucket S3 và Table DynamoDB của bạn ở đây
# Có thể dùng biến môi trường để quản lý tốt hơn trong production
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'your-unique-s3-bucket-name-12345') # THAY THẾ TÊN NÀY!
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'MyWebAppDataTable') # THAY THẾ TÊN NÀY!

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    if request.method == 'POST':
        user_name = request.form.get('user_name')
        message = request.form.get('message')

        if not user_name or not message:
            return render_template('index.html', error="Vui lòng điền đầy đủ thông tin.")

        item_id = str(uuid.uuid4()) # Tạo ID duy nhất

        try:
            # 1. Lưu dữ liệu vào DynamoDB
            table = dynamodb_client.Table(DYNAMODB_TABLE_NAME)
            table.put_item(
                Item={
                    'id': item_id,
                    'UserName': user_name,
                    'Message': message,
                    'Timestamp': boto3.util.current_time_millis()
                }
            )
            print(f"Dữ liệu đã được lưu vào DynamoDB: {item_id}")

            # 2. Tải lên "file" (nội dung message) lên S3
            s3_file_key = f"messages/{item_id}.txt"
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_file_key,
                Body=f"User: {user_name}\nMessage: {message}"
            )
            print(f"File đã được tải lên S3: {s3_file_key}")

            return render_template('index.html', success="Dữ liệu và file đã được xử lý thành công!")

        except Exception as e:
            print(f"Lỗi khi xử lý: {e}")
            return render_template('index.html', error=f"Đã xảy ra lỗi: {e}")

if __name__ == '__main__':
    # Chạy Flask ở chế độ debug để dễ phát triển,
    # nhưng KHÔNG BAO GIỜ dùng debug=True trong môi trường production!
    app.run(debug=True, host='0.0.0.0', port=5000) # Listen trên tất cả các interface