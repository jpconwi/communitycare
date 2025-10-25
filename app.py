import os
import flet as ft
import psycopg2
from datetime import datetime
import re
import base64
import io
from PIL import Image
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection - works both locally and globally"""
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        # Local development (NOT global)
        database_url = 'postgresql://postgres:jpconwi2005@localhost:5432/communitycare'
        print("🔧 Running in LOCAL mode")
    else:
        # Production on Render (GLOBAL)
        print("🌍 Running in GLOBAL mode")
    
    try:
        # Handle SSL for production (Render)
        if 'render.com' in database_url or 'postgres.railway.app' in database_url:
            conn = psycopg2.connect(database_url, sslmode='require')
        else:
            conn = psycopg2.connect(database_url)
        
        return conn
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        raise

def init_database():
    """Initialize the database tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create tables if they don't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            name TEXT NOT NULL,
            problem_type TEXT NOT NULL,
            location TEXT NOT NULL,
            issue TEXT NOT NULL,
            date TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            priority TEXT DEFAULT 'Medium',
            photo_data TEXT,
            latitude REAL,
            longitude REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            report_id INTEGER REFERENCES reports(id),
            message TEXT NOT NULL,
            type TEXT DEFAULT 'status_update',
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id SERIAL PRIMARY KEY,
            admin_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create admin user if not exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE email=%s", ('admin@community.com',))
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO users (username, password, email, role) VALUES (%s, %s, %s, %s)",
                ('admin', 'admin123', 'admin@community.com', 'admin')
            )
            print("✅ Admin user created")

        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database initialized successfully!")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

# Initialize database when app starts
init_database()

def main(page: ft.Page):
    page.title = "CommunityCare - Report System"
    page.window.width = 430
    page.window.height = 850
    page.window.resizable = False
    page.padding = 0
    page.theme_mode = "light"
    page.theme = ft.Theme(
        color_scheme_seed="#2563eb",
        font_family="Segoe UI, system-ui"
    )
    page.bgcolor = "#f8fafc"

    current_user = {"id": None, "username": None, "role": None}
    current_admin_tab = 0

    # PhotoState class for managing photo data
    class PhotoState:
        def __init__(self):
            self.photo_data = None
            self.photo_name = None

    # Global photo_state instance
    photo_state = PhotoState()

    def show_snack(message: str, color: str = "#10b981"):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color="white"),
            bgcolor=color,
            behavior=ft.SnackBarBehavior.FLOATING,
            elevation=8,
            shape=ft.RoundedRectangleBorder(radius=12)
        )
        page.snack_bar.open = True
        page.update()

    def validate_email(email):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def validate_phone(phone):
        pattern = r'^\+?1?\d{9,15}$'
        return re.match(pattern, phone) is not None

    def get_notifications_count():
        if current_user["id"]:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=FALSE", (current_user["id"],))
                count = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                return count
            except Exception as e:
                logger.error(f"Error getting notifications count: {e}")
                return 0
        return 0

    def add_notification(user_id, report_id, message, notification_type="status_update"):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notifications (user_id, report_id, message, type) VALUES (%s, %s, %s, %s)",
                (user_id, report_id, message, notification_type)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding notification: {e}")

    def add_admin_log(action, target_type, target_id=None, details=None):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO admin_logs (admin_id, action, target_type, target_id, details) VALUES (%s, %s, %s, %s, %s)",
                (current_user["id"], action, target_type, target_id, details)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding admin log: {e}")

    def get_report_stats():
        stats = {'total': 0, 'pending': 0, 'in_progress': 0, 'resolved': 0, 'my_reports': 0}
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM reports")
            stats['total'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reports WHERE status='Pending'")
            stats['pending'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reports WHERE status='In Progress'")
            stats['in_progress'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reports WHERE status='Resolved'")
            stats['resolved'] = cursor.fetchone()[0]
            
            if current_user["id"]:
                cursor.execute("SELECT COUNT(*) FROM reports WHERE user_id=%s", (current_user["id"],))
                stats['my_reports'] = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error getting report stats: {e}")
        return stats

    def modern_card(content, padding=20, margin=10, bgcolor="white"):
        return ft.Container(
            content=ft.Container(
                content=content,
                padding=padding,
                border_radius=16,
                bgcolor=bgcolor,
                shadow=ft.BoxShadow(
                    spread_radius=1,
                    blur_radius=15,
                    color=ft.Colors.BLACK12,
                    offset=ft.Offset(0, 4)
                )
            ),
            margin=margin,
        )

    def primary_button(text, on_click, width=None, icon=None):
        return ft.FilledButton(
            text=text,
            on_click=on_click,
            width=width,
            icon=icon,
            style=ft.ButtonStyle(
                color="white",
                bgcolor={"": "#2563eb", "hovered": "#1d4ed8"},
                padding=16,
                shape=ft.RoundedRectangleBorder(radius=12),
                elevation={"": 2, "hovered": 4}
            )
        )

    def secondary_button(text, on_click, width=None, icon=None):
        return ft.OutlinedButton(
            text=text,
            on_click=on_click,
            width=width,
            icon=icon,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=12),
                side=ft.BorderSide(1, "#2563eb")
            )
        )

    def modern_textfield(**kwargs):
        return ft.TextField(
            **kwargs,
            border_radius=12,
            border_color="#e2e8f0",
            focused_border_color="#2563eb",
            cursor_color="#2563eb",
            text_size=14
        )

    def status_badge(status):
        colors = {
            "Pending": ("#f59e0b", "#fef3c7"),
            "In Progress": ("#2563eb", "#dbeafe"),
            "Resolved": ("#10b981", "#d1fae5")
        }
        color, bgcolor = colors.get(status, ("#6b7280", "#f3f4f6"))
        return ft.Container(
            content=ft.Text(
                status,
                size=12,
                weight=ft.FontWeight.W_600,
                color=color
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            bgcolor=bgcolor,
            border_radius=20
        )

    def priority_badge(priority):
        colors = {
            "Low": ("#10b981", "#d1fae5"),
            "Medium": ("#f59e0b", "#fef3c7"),
            "High": ("#ef4444", "#fee2e2"),
            "Emergency": ("#dc2626", "#fecaca")
        }
        color, bgcolor = colors.get(priority, ("#6b7280", "#f3f4f6"))
        return ft.Container(
            content=ft.Text(
                priority,
                size=10,
                weight=ft.FontWeight.W_600,
                color=color
            ),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            bgcolor=bgcolor,
            border_radius=12
        )

    def compress_image(image_data, max_size=(800, 600), quality=85):
        """Compress image to reduce size"""
        try:
            image = Image.open(io.BytesIO(base64.b64decode(image_data)))
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            buffered = io.BytesIO()
            if image.mode in ('RGBA', 'LA'):
                # Convert RGBA to RGB for JPEG
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            
            image.save(buffered, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as e:
            logging.error(f"Error compressing image: {e}")
            return image_data

    # File pickers for photo upload - FIXED FOR WEB
    file_picker = ft.FilePicker()
    camera_picker = ft.FilePicker()

    def handle_file_upload(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                # In web environment, we need to use the file picker differently
                # The files are available as base64 data directly
                for file in e.files:
                    # Get the base64 data from the file object
                    if hasattr(file, 'read'):
                        # Local environment
                        photo_bytes = file.read()
                        photo_data = base64.b64encode(photo_bytes).decode('utf-8')
                    else:
                        # Web environment - get base64 data directly
                        photo_data = file.base64
                    
                    if not photo_data:
                        show_snack("Error: Could not read file", "#ef4444")
                        return
                        
                    # Compress the image
                    compressed_data = compress_image(photo_data)
            
                    photo_state.photo_data = compressed_data
                    photo_state.photo_name = file.name
                    update_photo_display()
                    show_snack("Photo uploaded successfully! 📸")
                    break  # Only process first file
            except Exception as ex:
                logger.error(f"Photo upload error: {str(ex)}")
                show_snack(f"Error uploading photo: {str(ex)}", "#ef4444")

    def handle_camera_photo(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                # Same logic as file upload for web compatibility
                for file in e.files:
                    if hasattr(file, 'read'):
                        photo_bytes = file.read()
                        photo_data = base64.b64encode(photo_bytes).decode('utf-8')
                    else:
                        photo_data = file.base64
                    
                    if not photo_data:
                        show_snack("Error: Could not read photo", "#ef4444")
                        return
                        
                    # Compress the image
                    compressed_data = compress_image(photo_data)
            
                    photo_state.photo_data = compressed_data
                    photo_state.photo_name = "camera_photo.jpg"
                    update_photo_display()
                    show_snack("Photo captured successfully! 📸")
                    break
            except Exception as ex:
                logger.error(f"Camera photo error: {str(ex)}")
                show_snack(f"Error processing photo: {str(ex)}", "#ef4444")

    def open_file_picker(e):
        file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["png", "jpg", "jpeg", "gif"],
            file_type=ft.FilePickerFileType.IMAGE
        )

    def open_camera_picker(e):
        # For web, camera picker works the same as file picker
        camera_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["png", "jpg", "jpeg"],
            file_type=ft.FilePickerFileType.IMAGE
        )

    # Set file picker handlers
    file_picker.on_result = handle_file_upload
    camera_picker.on_result = handle_camera_photo

    # Add file pickers to page overlay
    page.overlay.extend([file_picker, camera_picker])

    def update_photo_display():
        """Update the photo display - will be implemented in specific screens"""
        pass

    def login_screen():
        page.clean()

        email = modern_textfield(
            label="Email",
            width=350,
            prefix_icon=ft.Icons.EMAIL,
            hint_text="Enter your email"
        )
        password = modern_textfield(
            label="Password",
            password=True,
            can_reveal_password=True,
            width=350,
            prefix_icon=ft.Icons.LOCK,
            hint_text="Enter your password"
        )

        def do_login(e):
            if not email.value or not password.value:
                show_snack("Please enter both email and password!", "#f59e0b")
                return
                
            if not validate_email(email.value):
                show_snack("Please enter a valid email address!", "#f59e0b")
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, role, email FROM users WHERE email=%s AND password=%s",
                               (email.value, password.value))
                user = cursor.fetchone()
                cursor.close()
                conn.close()
                
                if user:
                    current_user["id"] = user[0]
                    current_user["username"] = user[1]
                    current_user["role"] = user[2]
                    show_snack(f"Welcome back, {user[1]}! 👋")
                    if user[2] == "admin":
                        admin_dashboard_screen()
                    else:
                        user_dashboard_screen()
                else:
                    show_snack("Invalid email or password! Please try again.", "#ef4444")
            except Exception as e:
                logger.error(f"Login error: {e}")
                show_snack("Login failed. Please try again.", "#ef4444")

        def go_register(e):
            register_screen()

        login_content = ft.Column([
            ft.Container(height=40),
            ft.Row([
                ft.Icon(ft.Icons.LOCATION_CITY_OUTLINED, size=40, color="#2563eb"),
                ft.Text("CommunityCare", size=28, weight=ft.FontWeight.BOLD, color="#1e293b"),
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("Report community issues with ease", size=16, color="#64748b", text_align=ft.TextAlign.CENTER),
            ft.Container(height=30),
            ft.Container(content=email, alignment=ft.alignment.center),
            ft.Container(content=password, alignment=ft.alignment.center),
            ft.Container(height=10),
            ft.Container(content=primary_button("Sign In", do_login, width=350, icon=ft.Icons.LOGIN), alignment=ft.alignment.center),
            ft.Container(height=10),
            ft.Row([
                ft.Text("Don't have an account?", color="#64748b"),
                ft.TextButton("Sign Up", on_click=go_register, style=ft.ButtonStyle(
                    color="#2563eb",
                    padding=ft.padding.symmetric(horizontal=8, vertical=4)
                ))
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=20),
            ft.Divider(height=1, color="#e2e8f0"),
            ft.Container(height=10),
            ft.Text("Demo Admin Account", size=12, color="#94a3b8", weight=ft.FontWeight.W_500),
            ft.Text("Email: admin@community.com", size=11, color="#64748b"),
            ft.Text("Password: admin123", size=11, color="#64748b"),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0)

        page.add(
            ft.Container(
                content=modern_card(login_content, padding=30),
                padding=20,
                alignment=ft.alignment.center,
                expand=True
            )
        )

    def register_screen():
        page.clean()

        username = modern_textfield(label="Full Name", width=350, prefix_icon=ft.Icons.PERSON)
        email = modern_textfield(label="Email", width=350, prefix_icon=ft.Icons.EMAIL)
        phone = modern_textfield(label="Phone (optional)", width=350, prefix_icon=ft.Icons.PHONE)
        password = modern_textfield(label="Password", password=True, can_reveal_password=True, width=350,
                                    prefix_icon=ft.Icons.LOCK)
        confirm_password = modern_textfield(label="Confirm Password", password=True, can_reveal_password=True,
                                            width=350, prefix_icon=ft.Icons.LOCK)

        def do_register(e):
            if not all([username.value, email.value, password.value, confirm_password.value]):
                show_snack("Please fill in all required fields!", "#f59e0b")
                return

            if not validate_email(email.value):
                show_snack("Please enter a valid email address!", "#f59e0b")
                return

            if phone.value and not validate_phone(phone.value):
                show_snack("Please enter a valid phone number!", "#f59e0b")
                return

            if password.value != confirm_password.value:
                show_snack("Passwords do not match!", "#f59e0b")
                return

            if len(password.value) < 6:
                show_snack("Password must be at least 6 characters long!", "#f59e0b")
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM users WHERE email=%s", (email.value,))
                if cursor.fetchone():
                    show_snack("Email already exists!", "#ef4444")
                    cursor.close()
                    conn.close()
                    return

                cursor.execute("INSERT INTO users (username, password, email, phone) VALUES (%s, %s, %s, %s)",
                               (username.value, password.value, email.value, phone.value))
                conn.commit()
                cursor.close()
                conn.close()
                show_snack("Account created successfully! 🎉")
                login_screen()
            except Exception as e:
                logger.error(f"Registration error: {e}")
                show_snack("Registration failed. Please try again.", "#ef4444")

        register_content = ft.Column([
            ft.Container(height=20),
            ft.Row([
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e: login_screen(),
                    icon_color="#64748b"
                ),
                ft.Text("Create Account", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
            ]),
            ft.Container(height=20),
            ft.Container(content=username, alignment=ft.alignment.center),
            ft.Container(content=email, alignment=ft.alignment.center),
            ft.Container(content=phone, alignment=ft.alignment.center),
            ft.Container(content=password, alignment=ft.alignment.center),
            ft.Container(content=confirm_password, alignment=ft.alignment.center),
            ft.Container(height=10),
            ft.Container(content=primary_button("Create Account", do_register, width=350, icon=ft.Icons.PERSON_ADD), alignment=ft.alignment.center),
        ], spacing=12)

        page.add(
            ft.Container(
                content=modern_card(register_content, padding=25),
                padding=20,
                expand=True
            )
        )

    def admin_dashboard_screen():
        page.clean()

        admin_tabs = ft.Tabs(
            selected_index=current_admin_tab,
            animation_duration=300,
            tabs=[
                ft.Tab(text="Reports", icon=ft.Icons.REPORT),
                ft.Tab(text="Users", icon=ft.Icons.PEOPLE),
                ft.Tab(text="Activity", icon=ft.Icons.HISTORY),
            ],
            expand=True
        )

        def on_tab_change(e):
            nonlocal current_admin_tab
            current_admin_tab = e.control.selected_index
            update_admin_content()

        admin_tabs.on_change = on_tab_change

        stats_cards_container = ft.Container()

        def create_stats_cards():
            stats = get_report_stats()
            return ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.REPORT, color=ft.Colors.BLUE_500),
                        ft.Text("Total", size=12),
                        ft.Text(str(stats['total']), size=16, weight=ft.FontWeight.BOLD)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=10,
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=10,
                    expand=True
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.PENDING_ACTIONS, color=ft.Colors.ORANGE),
                        ft.Text("Pending", size=12),
                        ft.Text(str(stats['pending']), size=16, weight=ft.FontWeight.BOLD)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=10,
                    bgcolor=ft.Colors.ORANGE_50,
                    border_radius=10,
                    expand=True
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.TRENDING_UP, color=ft.Colors.BLUE_700),
                        ft.Text("In Progress", size=12),
                        ft.Text(str(stats['in_progress']), size=16, weight=ft.FontWeight.BOLD)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=10,
                    bgcolor=ft.Colors.BLUE_50,
                    border_radius=10,
                    expand=True
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN),
                        ft.Text("Resolved", size=12),
                        ft.Text(str(stats['resolved']), size=16, weight=ft.FontWeight.BOLD)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=10,
                    bgcolor=ft.Colors.GREEN_50,
                    border_radius=10,
                    expand=True
                ),
            ])

        def refresh_stats():
            stats_cards_container.content = create_stats_cards()
            page.update()

        def create_reports_tab():
            reports_list = ft.ListView(expand=True, spacing=6)

            def load_reports():
                reports_list.controls.clear()
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT r.id, u.username, r.problem_type, r.location, r.issue, r.date, r.status, r.priority, r.photo_data, r.created_at, r.name
                        FROM reports r JOIN users u ON r.user_id = u.id ORDER BY r.id DESC
                    """)
                    data = cursor.fetchall()
                    cursor.close()
                    conn.close()

                    if not data:
                        reports_list.controls.append(
                            ft.Container(
                                content=ft.Text("No reports found.", color=ft.Colors.GREY_600),
                                padding=20,
                                alignment=ft.alignment.center
                            )
                        )
                    else:
                        for r in data:
                            status_color = {
                                "Pending": ft.Colors.ORANGE,
                                "In Progress": ft.Colors.BLUE,
                                "Resolved": ft.Colors.GREEN
                            }.get(r[6], ft.Colors.GREY)

                            def create_detail_handler(item=r):
                                return lambda e: open_report_detail(item)

                            has_photo = r[8] is not None

                            reports_list.controls.append(
                                ft.Card(
                                    content=ft.Container(
                                        content=ft.Column([
                                            ft.Row([
                                                ft.Icon(ft.Icons.REPORT_PROBLEM, color=status_color),
                                                ft.Text(f"Report #{r[0]}", size=14, weight=ft.FontWeight.BOLD, expand=True),
                                                status_badge(r[6]),
                                            ]),
                                            ft.Text(r[2], size=16, weight=ft.FontWeight.W_600),
                                            ft.Text(f"By: {r[1]} • {r[3]}", size=14, color=ft.Colors.GREY_600),
                                            ft.Text(f"Date: {r[5]}", size=12, color=ft.Colors.GREY_500),
                                            ft.Row([
                                                ft.Text("📷" if has_photo else "No photo", size=12, color=ft.Colors.GREY_500),
                                                ft.Container(expand=True),
                                                ft.FilledButton(
                                                    "View Details",
                                                    on_click=create_detail_handler(),
                                                    style=ft.ButtonStyle(padding=10)
                                                )
                                            ])
                                        ], spacing=8),
                                        padding=15
                                    ),
                                    margin=5
                                )
                            )
                except Exception as e:
                    logger.error(f"Error loading reports: {e}")
                    reports_list.controls.append(
                        ft.Container(
                            content=ft.Text("Error loading reports.", color=ft.Colors.RED),
                            padding=20,
                            alignment=ft.alignment.center
                        )
                    )
                page.update()

            def update_report_status(report_id, new_status):
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE reports SET status=%s WHERE id=%s", (new_status, report_id))
                    conn.commit()

                    cursor.execute("SELECT user_id FROM reports WHERE id=%s", (report_id,))
                    result = cursor.fetchone()
                    if result:
                        user_id = result[0]
                        add_notification(user_id, report_id, f"Your report status has been updated to {new_status}")

                    add_admin_log("UPDATE_STATUS", "report", report_id, f"Status changed to {new_status}")

                    cursor.close()
                    conn.close()
                    show_snack(f"Status updated to {new_status}!")
                    load_reports()
                    refresh_stats()
                except Exception as e:
                    logger.error(f"Error updating report status: {e}")
                    show_snack("Error updating status", "#ef4444")

            def open_report_detail(item):
                try:
                    report_id = item[0]
                    username = item[1]
                    problem_type = item[2]
                    location = item[3]
                    issue = item[4]
                    date = item[5]
                    status = item[6]
                    priority = item[7]
                    photo_data = item[8]
                    created_at = item[9]
                    reporter_name = item[10]

                    content_controls = [
                        ft.Row([
                            ft.Text(f"Report #{report_id}", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                            status_badge(status),
                        ]),
                        ft.Container(height=10),
                        ft.Text("Reporter Information", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.PERSON, size=16, color="#64748b"),
                                    ft.Text("Name:", size=14, color="#64748b", width=80),
                                    ft.Text(reporter_name, size=14, color="#1e293b", expand=True),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.EMAIL, size=16, color="#64748b"),
                                    ft.Text("Username:", size=14, color="#64748b", width=80),
                                    ft.Text(username, size=14, color="#1e293b", expand=True),
                                ]),
                            ], spacing=8),
                            padding=10,
                            bgcolor="#f8fafc",
                            border_radius=8,
                        ),
                        ft.Container(height=10),
                        ft.Text("Report Details", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.CATEGORY, size=16, color="#64748b"),
                                    ft.Text("Problem Type:", size=14, color="#64748b", width=100),
                                    ft.Text(problem_type, size=14, color="#1e293b", expand=True),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.LOCATION_ON, size=16, color="#64748b"),
                                    ft.Text("Location:", size=14, color="#64748b", width=100),
                                    ft.Text(location, size=14, color="#1e293b", expand=True),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.FLAG, size=16, color="#64748b"),
                                    ft.Text("Priority:", size=14, color="#64748b", width=100),
                                    priority_badge(priority.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").replace("🚨 ", "")),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=16, color="#64748b"),
                                    ft.Text("Report Date:", size=14, color="#64748b", width=100),
                                    ft.Text(date, size=14, color="#1e293b", expand=True),
                                ]),
                            ], spacing=8),
                            padding=10,
                            bgcolor="#f8fafc",
                            border_radius=8,
                        ),
                        ft.Container(height=10),
                        ft.Text("Description", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                        ft.Container(
                            content=ft.Text(issue, size=14, color="#475569"),
                            padding=15,
                            bgcolor="#f8fafc",
                            border_radius=8,
                        ),
                    ]

                    if photo_data:
                        content_controls.extend([
                            ft.Container(height=10),
                            ft.Text("Attached Photo", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                            ft.Container(
                                content=ft.Image(
                                    src_base64=photo_data,
                                    width=300,
                                    height=200,
                                    fit=ft.ImageFit.CONTAIN,
                                    border_radius=12,
                                ),
                                alignment=ft.alignment.center,
                                padding=10,
                                bgcolor="#f8fafc",
                                border_radius=12,
                            )
                        ])

                    content_controls.extend([
                        ft.Container(height=20),
                        ft.Row([
                            secondary_button("Mark In Progress", lambda e: [update_report_status(report_id, "In Progress"), close_dialog()]),
                            secondary_button("Mark Resolved", lambda e: [update_report_status(report_id, "Resolved"), close_dialog()]),
                        ]),
                    ])

                    page.dialog = ft.AlertDialog(
                        modal=True,
                        title=ft.Text("Report Details"),
                        content=ft.Container(
                            content=ft.Column(content_controls, spacing=12, scroll=ft.ScrollMode.ADAPTIVE),
                            width=400,
                            height=500
                        ),
                        actions=[
                            ft.TextButton("Close", on_click=close_dialog)
                        ]
                    )
                    page.dialog.open = True
                    page.update()
                except Exception as e:
                    logger.error(f"Error opening report detail: {e}")
                    show_snack("Error loading report details", "#ef4444")

            def close_dialog(e=None):
                page.dialog.open = False
                page.update()

            load_reports()

            return ft.Column([
                ft.Row([
                    ft.Text("Community Reports", size=20, weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_reports())
                ]),
                ft.Container(height=10),
                reports_list
            ])

        def create_users_tab():
            users_list = ft.ListView(expand=True, spacing=6)

            def load_users():
                users_list.controls.clear()
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, username, email, role, created_at FROM users ORDER BY id DESC")
                    data = cursor.fetchall()
                    cursor.close()
                    conn.close()

                    if not data:
                        users_list.controls.append(
                            ft.Container(
                                content=ft.Text("No users found.", color=ft.Colors.GREY_600),
                                padding=20,
                                alignment=ft.alignment.center
                            )
                        )
                    else:
                        for u in data:
                            role_color = ft.Colors.BLUE if u[3] == "admin" else ft.Colors.GREEN

                            users_list.controls.append(
                                ft.Card(
                                    content=ft.Container(
                                        content=ft.Column([
                                            ft.Row([
                                                ft.Icon(ft.Icons.PERSON, color=role_color),
                                                ft.Text(u[1], size=16, weight=ft.FontWeight.BOLD, expand=True),
                                                ft.Container(
                                                    content=ft.Text(u[3].upper(), size=12, color="white", weight=ft.FontWeight.BOLD),
                                                    bgcolor=role_color,
                                                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                                    border_radius=12
                                                )
                                            ]),
                                            ft.Text(u[2], size=14, color=ft.Colors.GREY_600),
                                            ft.Text(f"Joined: {u[4].strftime('%Y-%m-%d')}", size=12, color=ft.Colors.GREY_500),
                                        ], spacing=8),
                                        padding=15
                                    ),
                                    margin=5
                                )
                            )
                except Exception as e:
                    logger.error(f"Error loading users: {e}")
                    users_list.controls.append(
                        ft.Container(
                            content=ft.Text("Error loading users.", color=ft.Colors.RED),
                            padding=20,
                            alignment=ft.alignment.center
                        )
                    )
                page.update()

            load_users()

            return ft.Column([
                ft.Row([
                    ft.Text("User Management", size=20, weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_users())
                ]),
                ft.Container(height=10),
                users_list
            ])

        def create_activity_tab():
            activity_list = ft.ListView(expand=True, spacing=6)

            def load_activity():
                activity_list.controls.clear()
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT al.action, al.target_type, al.target_id, al.details, al.created_at, u.username
                        FROM admin_logs al JOIN users u ON al.admin_id = u.id ORDER BY al.created_at DESC LIMIT 50
                    """)
                    data = cursor.fetchall()
                    cursor.close()
                    conn.close()

                    if not data:
                        activity_list.controls.append(
                            ft.Container(
                                content=ft.Text("No activity logs found.", color=ft.Colors.GREY_600),
                                padding=20,
                                alignment=ft.alignment.center
                            )
                        )
                    else:
                        for log in data:
                            action_color = {
                                "DELETE": ft.Colors.RED,
                                "UPDATE_STATUS": ft.Colors.BLUE,
                                "UPDATE_ROLE": ft.Colors.ORANGE,
                            }.get(log[0], ft.Colors.GREEN)

                            activity_list.controls.append(
                                ft.Card(
                                    content=ft.Container(
                                        content=ft.Column([
                                            ft.Row([
                                                ft.Icon(ft.Icons.HISTORY, color=action_color),
                                                ft.Text(log[0], size=14, weight=ft.FontWeight.BOLD, expand=True),
                                                ft.Text(log[5], size=12, color=ft.Colors.GREY_600),
                                            ]),
                                            ft.Text(f"{log[1]} #{log[2] if log[2] else 'N/A'}", size=12, color=ft.Colors.GREY_600),
                                            ft.Text(log[3] if log[3] else "No details", size=12, color=ft.Colors.GREY_500),
                                            ft.Text(log[4].strftime('%Y-%m-%d %H:%M'), size=10, color=ft.Colors.GREY_400),
                                        ], spacing=6),
                                        padding=12
                                    ),
                                    margin=5
                                )
                            )
                except Exception as e:
                    logger.error(f"Error loading activity: {e}")
                    activity_list.controls.append(
                        ft.Container(
                            content=ft.Text("Error loading activity logs.", color=ft.Colors.RED),
                            padding=20,
                            alignment=ft.alignment.center
                        )
                    )
                page.update()

            load_activity()

            return ft.Column([
                ft.Row([
                    ft.Text("Activity Log", size=20, weight=ft.FontWeight.BOLD),
                    ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: load_activity())
                ]),
                ft.Container(height=10),
                activity_list
            ])

        def update_admin_content():
            content_area.controls.clear()
            if current_admin_tab == 0:
                content_area.controls.append(create_reports_tab())
            elif current_admin_tab == 1:
                content_area.controls.append(create_users_tab())
            elif current_admin_tab == 2:
                content_area.controls.append(create_activity_tab())
            page.update()

        content_area = ft.Column(scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        stats_cards_container.content = create_stats_cards()
        update_admin_content()

        def logout(e):
            current_user["id"] = None
            current_user["username"] = None
            current_user["role"] = None
            login_screen()

        page.add(
            ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text("Admin Dashboard", size=24, weight=ft.FontWeight.BOLD),
                            ft.Text("Manage community reports", size=14, color=ft.Colors.GREY_600),
                        ], expand=True),
                        ft.IconButton(ft.Icons.LOGOUT, on_click=logout, tooltip="Logout")
                    ]),
                    padding=20
                ),
                ft.Container(content=stats_cards_container, padding=ft.padding.symmetric(horizontal=20)),
                ft.Container(height=10),
                ft.Container(
                    content=ft.Column([
                        admin_tabs,
                        ft.Container(content=content_area, expand=True)
                    ], expand=True),
                    expand=True
                )
            ], expand=True)
        )

    def user_dashboard_screen():
        page.clean()

        # Create report form components
        problem_type = ft.Dropdown(
            label="Problem Type",
            options=[
                ft.dropdown.Option("🚗 Traffic Issue"),
                ft.dropdown.Option("🗑️ Waste Management"),
                ft.dropdown.Option("💧 Water Problem"),
                ft.dropdown.Option("⚡ Power Outage"),
                ft.dropdown.Option("🛣️ Road Damage"),
                ft.dropdown.Option("🌳 Environmental Issue"),
                ft.dropdown.Option("🏢 Public Facility"),
                ft.dropdown.Option("🚨 Emergency"),
                ft.dropdown.Option("📝 Other"),
            ],
            width=350
        )
        
        location = modern_textfield(
            label="Location",
            width=350,
            hint_text="Enter the exact location"
        )
        
        issue = modern_textfield(
            label="Issue Description",
            multiline=True,
            min_lines=3,
            width=350,
            hint_text="Describe the problem in detail..."
        )
        
        priority = ft.Dropdown(
            label="Priority",
            options=[
                ft.dropdown.Option("🟢 Low"),
                ft.dropdown.Option("🟡 Medium"),
                ft.dropdown.Option("🔴 High"),
                ft.dropdown.Option("🚨 Emergency"),
            ],
            value="🟡 Medium",
            width=350
        )

        photo_display = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.PHOTO_CAMERA_OUTLINED, size=48, color="#cbd5e1"),
                ft.Text("No photo selected", size=14, color="#94a3b8"),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            padding=20,
            bgcolor="#f8fafc",
            border_radius=12,
            border=ft.border.all(1, "#e2e8f0"),
            alignment=ft.alignment.center,
            visible=True
        )

        photo_preview = ft.Container(
            content=ft.Column([
                ft.Image(
                    src_base64=photo_state.photo_data,
                    width=200,
                    height=150,
                    fit=ft.ImageFit.COVER,
                    border_radius=8,
                ),
                ft.Text(photo_state.photo_name or "Uploaded photo", size=12, color="#64748b"),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
            padding=10,
            bgcolor="#f8fafc",
            border_radius=12,
            border=ft.border.all(1, "#e2e8f0"),
            alignment=ft.alignment.center,
            visible=False
        )

        def update_photo_display():
            if photo_state.photo_data:
                photo_display.visible = False
                photo_preview.visible = True
                photo_preview.content.controls[0].src_base64 = photo_state.photo_data
                photo_preview.content.controls[1].value = photo_state.photo_name or "Uploaded photo"
            else:
                photo_display.visible = True
                photo_preview.visible = False
            page.update()

        def submit_report(e):
            if not all([problem_type.value, location.value, issue.value]):
                show_snack("Please fill in all required fields!", "#f59e0b")
                return

            try:
                date = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO reports (user_id, name, problem_type, location, issue, date, priority, photo_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    current_user["id"],
                    current_user["username"],
                    problem_type.value,
                    location.value,
                    issue.value,
                    date,
                    priority.value,
                    photo_state.photo_data
                ))
                
                conn.commit()
                cursor.close()
                conn.close()

                # Reset form
                problem_type.value = None
                location.value = ""
                issue.value = ""
                priority.value = "🟡 Medium"
                photo_state.photo_data = None
                photo_state.photo_name = None
                update_photo_display()
                
                show_snack("Report submitted successfully! ✅")
                
            except Exception as ex:
                logger.error(f"Submit report error: {str(ex)}")
                show_snack(f"Error submitting report: {str(ex)}", "#ef4444")

        def logout(e):
            current_user["id"] = None
            current_user["username"] = None
            current_user["role"] = None
            login_screen()

        # Initialize photo display
        update_photo_display()

        page.add(
            ft.Column([
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"Welcome, {current_user['username']}! 👋", size=20, weight=ft.FontWeight.BOLD),
                            ft.Text("Report community issues", size=14, color=ft.Colors.GREY_600),
                        ], expand=True),
                        ft.IconButton(ft.Icons.LOGOUT, on_click=logout, tooltip="Logout")
                    ]),
                    padding=20
                ),
                
                ft.Container(
                    content=ft.Column([
                        ft.Text("New Report", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(height=10),
                        ft.Container(content=problem_type, alignment=ft.alignment.center),
                        ft.Container(content=location, alignment=ft.alignment.center),
                        ft.Container(content=issue, alignment=ft.alignment.center),
                        ft.Container(content=priority, alignment=ft.alignment.center),
                        ft.Container(height=10),
                        ft.Text("Add Photo (Optional)", size=16, weight=ft.FontWeight.W_600),
                        ft.Row([
                            secondary_button("Take Photo", open_camera_picker),
                            secondary_button("Upload Photo", open_file_picker),
                        ], alignment=ft.MainAxisAlignment.CENTER),
                        ft.Container(height=10),
                        ft.Stack([photo_display, photo_preview]),
                        ft.Container(height=20),
                        ft.Container(content=primary_button("Submit Report", submit_report, width=350), alignment=ft.alignment.center),
                    ], spacing=12),
                    padding=20
                )
            ], scroll=ft.ScrollMode.ADAPTIVE)
        )

    # Start with login screen
    login_screen()

# Run the app
if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER, port=8501)
