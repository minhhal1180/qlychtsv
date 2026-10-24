"""Ten deliberate business defects for the testing exercise. Never bypass RBAC."""

BUGS = {
    "B01": "Chấp nhận tiêu đề chỉ có khoảng trắng",
    "B02": "Chấp nhận loại yêu cầu đã ngừng hoạt động",
    "B03": "Cho hủy yêu cầu sau khi cán bộ tiếp nhận",
    "B04": "Cho hoàn tất mà không có kết quả xử lý",
    "B05": "Cho từ chối mà không có lý do",
    "B06": "Bổ sung không chuyển về trạng thái đang xử lý",
    "B07": "Cho mở lại yêu cầu đã bị từ chối",
    "B08": "Tìm kiếm bỏ sót mã yêu cầu, chỉ tìm theo tiêu đề",
    "B09": "Đánh dấu thông báo đã đọc nhưng không lưu",
    "B10": "Hoàn tất không ghi lịch sử chuyển trạng thái",
}


def enabled(app, bug_id):
    return app.config["TRAINING_BUGS"] and bug_id in BUGS
