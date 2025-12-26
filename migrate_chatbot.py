#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Migration script để tạo bảng ChatConversation trong database hiện có
Chạy script này để nâng cấp database với tính năng chatbot memory
"""

from app import app, db
from models import ChatConversation

def migrate():
    with app.app_context():
        print("🔄 Đang tạo bảng ChatConversation...")
        try:
            # Tạo bảng mới (chỉ tạo bảng chưa tồn tại)
            db.create_all()
            print("✅ Migration hoàn tất!")
            print("📊 Bảng ChatConversation đã được tạo trong database.")
            print("\n💡 Chatbot giờ đã có khả năng nhớ lịch sử hội thoại!")
        except Exception as e:
            print(f"❌ Lỗi migration: {e}")
            return False
    return True

if __name__ == "__main__":
    migrate()
