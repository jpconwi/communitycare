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

    # File pickers for photo upload
    file_picker = ft.FilePicker()
    camera_picker = ft.FilePicker()

    def handle_file_upload(e: ft.FilePickerResultEvent):
        if e.files and e.files[0]:
            try:
                photo_file = e.files[0]
                # Read file content
                photo_bytes = photo_file.read()
                if not photo_bytes:
                    show_snack("Error: Could not read file", "#ef4444")
                    return
                    
                photo_data = base64.b64encode(photo_bytes).decode('utf-8')
        
                # Compress the image
                compressed_data = compress_image(photo_data)
        
                photo_state.photo_data = compressed_data
                photo_state.photo_name = photo_file.name
                update_photo_display()
                show_snack("Photo uploaded successfully! 📸")
            except Exception as ex:
                logger.error(f"Photo upload error: {str(ex)}")
                show_snack(f"Error uploading photo: {str(ex)}", "#ef4444")

    def handle_camera_photo(e: ft.FilePickerResultEvent):
        if e.files and e.files[0]:
            try:
                photo_file = e.files[0]
                photo_bytes = photo_file.read()
                if not photo_bytes:
                    show_snack("Error: Could not read photo", "#ef4444")
                    return
                    
                photo_data = base64.b64encode(photo_bytes).decode('utf-8')
        
                # Compress the image
                compressed_data = compress_image(photo_data)
        
                photo_state.photo_data = compressed_data
                photo_state.photo_name = "camera_photo.jpg"
                update_photo_display()
                show_snack("Photo captured successfully! 📸")
        
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
        """Update the photo display in the user dashboard"""
        # This function will be defined in user_dashboard_screen
        pass

    def login_screen():
        page.clean()

        email = modern_textfield(
            label="Email",
            width=280,
            prefix_icon=ft.Icons.EMAIL,
            hint_text="Enter your email"
        )
        password = modern_textfield(
            label="Password",
            password=True,
            can_reveal_password=True,
            width=280,
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
            email,
            password,
            ft.Container(height=10),
            primary_button("Sign In", do_login, width=280, icon=ft.Icons.LOGIN),
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
                alignment=ft.alignment.center
            )
        )

    def register_screen():
        page.clean()

        username = modern_textfield(label="Full Name", width=280, prefix_icon=ft.Icons.PERSON)
        email = modern_textfield(label="Email", width=280, prefix_icon=ft.Icons.EMAIL)
        phone = modern_textfield(label="Phone (optional)", width=280, prefix_icon=ft.Icons.PHONE)
        password = modern_textfield(label="Password", password=True, can_reveal_password=True, width=280,
                                    prefix_icon=ft.Icons.LOCK)
        confirm_password = modern_textfield(label="Confirm Password", password=True, can_reveal_password=True,
                                            width=280, prefix_icon=ft.Icons.LOCK)

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
            username,
            email,
            phone,
            password,
            confirm_password,
            ft.Container(height=10),
            primary_button("Create Account", do_register, width=280, icon=ft.Icons.PERSON_ADD),
        ], spacing=12)

        page.add(
            ft.Container(
                content=modern_card(register_content, padding=25),
                padding=20
            )
        )

    def admin_dashboard_screen():
        page.clean()

        admin_tabs = ft.Tabs(
            selected_index=current_admin_tab,
            animation_duration=300,
            tabs=[
                ft.Tab(text="Community Reports", icon=ft.Icons.SUPERVISOR_ACCOUNT),
                ft.Tab(text="User Management", icon=ft.Icons.PEOPLE),
                ft.Tab(text="Activity Log", icon=ft.Icons.HISTORY),
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

        def create_community_reports_tab():
            reports_list = ft.ListView(expand=True, spacing=6)

            def load_community_reports():
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
                        reports_list.controls.append(ft.Text("No community reports found.", color=ft.Colors.GREY_600))
                    else:
                        for r in data:
                            status_color = {
                                "Pending": ft.Colors.ORANGE,
                                "In Progress": ft.Colors.BLUE,
                                "Resolved": ft.Colors.GREEN
                            }.get(r[6], ft.Colors.GREY)

                            def create_delete_handler(rid=r[0]):
                                return lambda e: show_delete_dialog(rid)

                            def create_detail_handler(item=r):
                                return lambda e: open_report_detail(item)

                            has_photo = r[8] is not None

                            reports_list.controls.append(
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.REPORT_PROBLEM, color=status_color),
                                    title=ft.Text(r[2], weight=ft.FontWeight.W_600),
                                    subtitle=ft.Text(f"By: {r[1]} • {r[3]} • {r[6]}" + (" 📷" if has_photo else "")),
                                    trailing=ft.PopupMenuButton(
                                        icon=ft.Icons.MORE_VERT,
                                        items=[
                                            ft.PopupMenuItem(
                                                text="View Details",
                                                on_click=create_detail_handler()
                                            ),
                                            ft.PopupMenuItem(
                                                text="Mark In Progress",
                                                on_click=lambda e, rid=r[0]: update_report_status(rid, "In Progress")
                                            ),
                                            ft.PopupMenuItem(
                                                text="Mark Resolved",
                                                on_click=lambda e, rid=r[0]: update_report_status(rid, "Resolved")
                                            ),
                                            ft.PopupMenuItem(
                                                text="Delete",
                                                on_click=create_delete_handler()
                                            ),
                                        ]
                                    ),
                                )
                            )
                except Exception as e:
                    logger.error(f"Error loading community reports: {e}")
                    reports_list.controls.append(ft.Text("Error loading reports.", color=ft.Colors.RED))
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
                    load_community_reports()
                    refresh_stats()
                except Exception as e:
                    logger.error(f"Error updating report status: {e}")
                    show_snack("Error updating status", "#ef4444")

            def delete_report(report_id):
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT problem_type, location FROM reports WHERE id=%s", (report_id,))
                    report = cursor.fetchone()

                    cursor.execute("DELETE FROM reports WHERE id=%s", (report_id,))
                    conn.commit()

                    if report:
                        add_admin_log("DELETE", "report", report_id, f"Deleted: {report[0]} - {report[1]}")

                    cursor.close()
                    conn.close()
                    show_snack("Report deleted successfully!")
                    load_community_reports()
                    refresh_stats()
                except Exception as e:
                    logger.error(f"Error deleting report: {e}")
                    show_snack("Error deleting report", "#ef4444")

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

                    # Clean problem type and priority
                    clean_problem_type = problem_type.split(" ", 1)[-1] if " " in problem_type else problem_type
                    clean_priority = priority.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").replace("🚨 ", "")

                    # Format created_at datetime
                    created_at_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "N/A"

                    content_controls = [
                        ft.Row([
                            ft.Text(f"Report #{report_id}", size=20, weight=ft.FontWeight.BOLD, color="#1e293b",
                                    expand=True),
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
                                    ft.Text(clean_problem_type, size=14, color="#1e293b", expand=True),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.LOCATION_ON, size=16, color="#64748b"),
                                    ft.Text("Location:", size=14, color="#64748b", width=100),
                                    ft.Text(location, size=14, color="#1e293b", expand=True),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.FLAG, size=16, color="#64748b"),
                                    ft.Text("Priority:", size=14, color="#64748b", width=100),
                                    priority_badge(clean_priority),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=16, color="#64748b"),
                                    ft.Text("Report Date:", size=14, color="#64748b", width=100),
                                    ft.Text(date, size=14, color="#1e293b", expand=True),
                                ]),
                                ft.Row([
                                    ft.Icon(ft.Icons.SCHEDULE, size=16, color="#64748b"),
                                    ft.Text("Created At:", size=14, color="#64748b", width=100),
                                    ft.Text(created_at_str, size=14, color="#1e293b", expand=True),
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
                                    width=380,
                                    height=280,
                                    fit=ft.ImageFit.CONTAIN,
                                    border_radius=12,
                                ),
                                alignment=ft.alignment.center,
                                padding=10,
                                bgcolor="#f8fafc",
                                border_radius=12,
                                border=ft.border.all(1, "#e2e8f0")
                            )
                        ])
                    else:
                        content_controls.extend([
                            ft.Container(height=10),
                            ft.Container(
                                content=ft.Column([
                                    ft.Row([
                                        ft.Icon(ft.Icons.PHOTO_CAMERA, size=20, color="#94a3b8"),
                                        ft.Text("No Photo Attached", size=16, weight=ft.FontWeight.W_600, color="#64748b"),
                                    ]),
                                    ft.Container(height=15),
                                    ft.Icon(ft.Icons.PHOTO_CAMERA_OUTLINED, size=64, color="#cbd5e1"),
                                    ft.Container(height=8),
                                    ft.Text("No photo was attached to this report", size=14, color="#94a3b8", text_align=ft.TextAlign.CENTER),
                                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                                padding=30,
                                bgcolor="#f8fafc",
                                border_radius=12,
                                border=ft.border.all(1, "#e2e8f0"),
                                alignment=ft.alignment.center
                            )
                        ])

                    content_controls.extend([
                        ft.Container(height=20),
                        ft.Row([
                            secondary_button(
                                "Mark In Progress",
                                lambda e: [update_report_status(report_id, "In Progress"), close_dialog()],
                                icon=ft.Icons.UPDATE
                            ),
                            secondary_button(
                                "Mark Resolved",
                                lambda e: [update_report_status(report_id, "Resolved"), close_dialog()],
                                icon=ft.Icons.CHECK_CIRCLE
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                    ])

                    page.dialog = ft.AlertDialog(
                        modal=True,
                        title=ft.Row([
                            ft.Icon(ft.Icons.REPORT_PROBLEM, color="#2563eb"),
                            ft.Text("Report Details", size=18, weight=ft.FontWeight.BOLD),
                        ]),
                        content=ft.Container(
                            content=ft.Column(content_controls, spacing=12, scroll=ft.ScrollMode.ADAPTIVE),
                            width=420,
                            height=650
                        ),
                        actions=[
                            ft.TextButton("Close", on_click=lambda e: close_dialog())
                        ],
                        shape=ft.RoundedRectangleBorder(radius=16)
                    )
                    page.dialog.open = True
                    page.update()
                except Exception as e:
                    logger.error(f"Error opening report detail: {e}")
                    show_snack("Error loading report details", "#ef4444")

            def show_delete_dialog(report_id):
                def confirm_delete(e):
                    delete_report(report_id)
                    page.dialog.open = False
                    page.update()

                page.dialog = ft.AlertDialog(
                    title=ft.Text("Confirm Delete"),
                    content=ft.Text("Are you sure you want to delete this report? This action cannot be undone."),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
                        ft.TextButton("Delete", on_click=confirm_delete, style=ft.ButtonStyle(color=ft.Colors.RED)),
                    ]
                )
                page.dialog.open = True
                page.update()

            def close_dialog(e=None):
                page.dialog.open = False
                page.update()

            load_community_reports()

            return ft.Column([
                ft.Row([
                    ft.Text("Community Reports", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        on_click=lambda e: load_community_reports(),
                        icon_color="#64748b",
                        tooltip="Refresh"
                    )
                ]),
                ft.Container(height=10),
                reports_list
            ])

        def create_user_management_tab():
            users_list = ft.ListView(expand=True, spacing=6)

            def load_users():
                users_list.controls.clear()
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, username, email, phone, role, created_at FROM users ORDER BY id DESC")
                    data = cursor.fetchall()
                    cursor.close()
                    conn.close()

                    if not data:
                        users_list.controls.append(ft.Text("No users found.", color=ft.Colors.GREY_600))
                    else:
                        for u in data:
                            role_color = ft.Colors.BLUE if u[4] == "admin" else ft.Colors.GREEN

                            def create_delete_handler(uid=u[0]):
                                return lambda e: show_delete_user_dialog(uid)

                            users_list.controls.append(
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.PERSON, color=role_color),
                                    title=ft.Text(u[1], weight=ft.FontWeight.W_600),
                                    subtitle=ft.Text(f"{u[2]} • {u[4]}"),
                                    trailing=ft.PopupMenuButton(
                                        icon=ft.Icons.MORE_VERT,
                                        items=[
                                            ft.PopupMenuItem(
                                                text="Make Admin",
                                                on_click=lambda e, uid=u[0]: update_user_role(uid, "admin")
                                            ),
                                            ft.PopupMenuItem(
                                                text="Make User",
                                                on_click=lambda e, uid=u[0]: update_user_role(uid, "user")
                                            ),
                                            ft.PopupMenuItem(
                                                text="Delete User",
                                                on_click=create_delete_handler()
                                            ),
                                        ]
                                    ),
                                )
                            )
                except Exception as e:
                    logger.error(f"Error loading users: {e}")
                    users_list.controls.append(ft.Text("Error loading users.", color=ft.Colors.RED))
                page.update()

            def update_user_role(user_id, new_role):
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET role=%s WHERE id=%s", (new_role, user_id))
                    conn.commit()

                    add_admin_log("UPDATE_ROLE", "user", user_id, f"Role changed to {new_role}")

                    cursor.close()
                    conn.close()
                    show_snack(f"User role updated to {new_role}!")
                    load_users()
                except Exception as e:
                    logger.error(f"Error updating user role: {e}")
                    show_snack("Error updating user role", "#ef4444")

            def delete_user(user_id):
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()

                    cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
                    username = cursor.fetchone()[0]

                    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
                    conn.commit()

                    add_admin_log("DELETE", "user", user_id, f"Deleted user: {username}")

                    cursor.close()
                    conn.close()
                    show_snack("User deleted successfully!")
                    load_users()
                except Exception as e:
                    logger.error(f"Error deleting user: {e}")
                    show_snack("Error deleting user", "#ef4444")

            def show_delete_user_dialog(user_id):
                def confirm_delete(e):
                    delete_user(user_id)
                    page.dialog.open = False
                    page.update()

                page.dialog = ft.AlertDialog(
                    title=ft.Text("Confirm Delete"),
                    content=ft.Text("Are you sure you want to delete this user? This action cannot be undone."),
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
                        ft.TextButton("Delete", on_click=confirm_delete, style=ft.ButtonStyle(color=ft.Colors.RED)),
                    ]
                )
                page.dialog.open = True
                page.update()

            load_users()

            return ft.Column([
                ft.Row([
                    ft.Text("User Management", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        on_click=lambda e: load_users(),
                        icon_color="#64748b",
                        tooltip="Refresh"
                    )
                ]),
                ft.Container(height=10),
                users_list
            ])

        def create_activity_log_tab():
            logs_list = ft.ListView(expand=True, spacing=6)

            def load_activity_logs():
                logs_list.controls.clear()
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
                        logs_list.controls.append(ft.Text("No activity logs found.", color=ft.Colors.GREY_600))
                    else:
                        for log in data:
                            action_color = {
                                "DELETE": ft.Colors.RED,
                                "UPDATE_STATUS": ft.Colors.BLUE,
                                "UPDATE_ROLE": ft.Colors.ORANGE,
                            }.get(log[0], ft.Colors.GREEN)

                            logs_list.controls.append(
                                ft.ListTile(
                                    leading=ft.Icon(ft.Icons.HISTORY, color=action_color),
                                    title=ft.Text(log[0], weight=ft.FontWeight.W_600),
                                    subtitle=ft.Text(f"{log[5]} • {log[1]} #{log[2] if log[2] else 'N/A'}"),
                                    trailing=ft.Text(log[4].strftime("%m/%d %H:%M"), size=12, color=ft.Colors.GREY),
                                )
                            )
                except Exception as e:
                    logger.error(f"Error loading activity logs: {e}")
                    logs_list.controls.append(ft.Text("Error loading activity logs.", color=ft.Colors.RED))
                page.update()

            load_activity_logs()

            return ft.Column([
                ft.Row([
                    ft.Text("Activity Log", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        on_click=lambda e: load_activity_logs(),
                        icon_color="#64748b",
                        tooltip="Refresh"
                    )
                ]),
                ft.Container(height=10),
                logs_list
            ])

        def update_admin_content():
            if current_admin_tab == 0:
                admin_content.content = create_community_reports_tab()
            elif current_admin_tab == 1:
                admin_content.content = create_user_management_tab()
            elif current_admin_tab == 2:
                admin_content.content = create_activity_log_tab()
            page.update()

        admin_content = ft.Container(
            content=create_community_reports_tab(),
            expand=True
        )

        stats_cards_container.content = create_stats_cards()

        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("Admin Dashboard", size=24, weight=ft.FontWeight.BOLD, color="#1e293b"),
                    ft.Text("Manage community reports and users", size=14, color="#64748b"),
                ], expand=True),
                ft.IconButton(
                    icon=ft.Icons.LOGOUT,
                    on_click=lambda e: [logout(), show_snack("Logged out successfully!")],
                    icon_color="#64748b",
                    tooltip="Logout"
                )
            ]),
            padding=20,
            bgcolor="white",
            border_radius=16,
            margin=ft.margin.only(bottom=10)
        )

        page.add(
            ft.Column([
                header,
                ft.Container(height=10),
                stats_cards_container,
                ft.Container(height=10),
                ft.Container(
                    content=ft.Column([
                        admin_tabs,
                        ft.Container(
                            content=admin_content,
                            expand=True
                        )
                    ], expand=True),
                    expand=True
                )
            ], expand=True)
        )

    def user_dashboard_screen():
        page.clean()

        stats_cards_container = ft.Container()
        reports_list = ft.ListView(expand=True, spacing=6)

        def create_stats_cards():
            stats = get_report_stats()
            return ft.Row([
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.REPORT, color=ft.Colors.BLUE_500),
                        ft.Text("My Reports", size=12),
                        ft.Text(str(stats['my_reports']), size=16, weight=ft.FontWeight.BOLD)
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

        def load_my_reports():
            reports_list.controls.clear()
            if not current_user["id"]:
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, problem_type, location, issue, date, status, priority, photo_data, created_at
                    FROM reports WHERE user_id=%s ORDER BY id DESC
                """, (current_user["id"],))
                data = cursor.fetchall()
                cursor.close()
                conn.close()

                if not data:
                    reports_list.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.REPORT_PROBLEM_OUTLINED, size=48, color="#cbd5e1"),
                                ft.Text("No reports yet", size=16, color="#64748b", weight=ft.FontWeight.W_500),
                                ft.Text("Submit your first community issue report!", size=14, color="#94a3b8"),
                                ft.Container(height=10),
                                primary_button("Report Issue", lambda e: report_issue_screen(), icon=ft.Icons.ADD)
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                            padding=40,
                            alignment=ft.alignment.center
                        )
                    )
                else:
                    for r in data:
                        has_photo = r[7] is not None

                        def create_detail_handler(item=r):
                            return lambda e: open_report_detail(item)

                        reports_list.controls.append(
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.REPORT_PROBLEM, color={
                                    "Pending": ft.Colors.ORANGE,
                                    "In Progress": ft.Colors.BLUE,
                                    "Resolved": ft.Colors.GREEN
                                }.get(r[5], ft.Colors.GREY)),
                                title=ft.Text(r[1], weight=ft.FontWeight.W_600),
                                subtitle=ft.Text(f"{r[2]} • {r[5]}" + (" 📷" if has_photo else "")),
                                trailing=ft.Row([
                                    status_badge(r[5]),
                                    ft.IconButton(
                                        icon=ft.Icons.CHEVRON_RIGHT,
                                        on_click=create_detail_handler(),
                                        icon_color="#64748b",
                                        icon_size=20
                                    )
                                ], width=100, spacing=0),
                                on_click=create_detail_handler()
                            )
                        )
            except Exception as e:
                logger.error(f"Error loading reports: {e}")
                reports_list.controls.append(ft.Text("Error loading reports.", color=ft.Colors.RED))
            page.update()

        def open_report_detail(item):
            try:
                report_id = item[0]
                problem_type = item[1]
                location = item[2]
                issue = item[3]
                date = item[4]
                status = item[5]
                priority = item[6]
                photo_data = item[7]
                created_at = item[8]

                # Clean problem type and priority
                clean_problem_type = problem_type.split(" ", 1)[-1] if " " in problem_type else problem_type
                clean_priority = priority.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").replace("🚨 ", "")

                # Format created_at datetime
                created_at_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "N/A"

                content_controls = [
                    ft.Row([
                        ft.Text(f"Report #{report_id}", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                        status_badge(status),
                    ]),
                    ft.Container(height=10),

                    ft.Text("Report Details", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.CATEGORY, size=16, color="#64748b"),
                                ft.Text("Problem Type:", size=14, color="#64748b", width=100),
                                ft.Text(clean_problem_type, size=14, color="#1e293b", expand=True),
                            ]),
                            ft.Row([
                                ft.Icon(ft.Icons.LOCATION_ON, size=16, color="#64748b"),
                                ft.Text("Location:", size=14, color="#64748b", width=100),
                                ft.Text(location, size=14, color="#1e293b", expand=True),
                            ]),
                            ft.Row([
                                ft.Icon(ft.Icons.FLAG, size=16, color="#64748b"),
                                ft.Text("Priority:", size=14, color="#64748b", width=100),
                                priority_badge(clean_priority),
                            ]),
                            ft.Row([
                                ft.Icon(ft.Icons.CALENDAR_TODAY, size=16, color="#64748b"),
                                ft.Text("Report Date:", size=14, color="#64748b", width=100),
                                ft.Text(date, size=14, color="#1e293b", expand=True),
                            ]),
                            ft.Row([
                                ft.Icon(ft.Icons.SCHEDULE, size=16, color="#64748b"),
                                ft.Text("Created At:", size=14, color="#64748b", width=100),
                                ft.Text(created_at_str, size=14, color="#1e293b", expand=True),
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
                                width=380,
                                height=280,
                                fit=ft.ImageFit.CONTAIN,
                                border_radius=12,
                            ),
                            alignment=ft.alignment.center,
                            padding=10,
                            bgcolor="#f8fafc",
                            border_radius=12,
                            border=ft.border.all(1, "#e2e8f0")
                        )
                    ])
                else:
                    content_controls.extend([
                        ft.Container(height=10),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.PHOTO_CAMERA, size=20, color="#94a3b8"),
                                    ft.Text("No Photo Attached", size=16, weight=ft.FontWeight.W_600, color="#64748b"),
                                ]),
                                ft.Container(height=15),
                                ft.Icon(ft.Icons.PHOTO_CAMERA_OUTLINED, size=64, color="#cbd5e1"),
                                ft.Container(height=8),
                                ft.Text("No photo was attached to this report", size=14, color="#94a3b8", text_align=ft.TextAlign.CENTER),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                            padding=30,
                            bgcolor="#f8fafc",
                            border_radius=12,
                            border=ft.border.all(1, "#e2e8f0"),
                            alignment=ft.alignment.center
                        )
                    ])

                page.dialog = ft.AlertDialog(
                    modal=True,
                    title=ft.Row([
                        ft.Icon(ft.Icons.REPORT_PROBLEM, color="#2563eb"),
                        ft.Text("Report Details", size=18, weight=ft.FontWeight.BOLD),
                    ]),
                    content=ft.Container(
                        content=ft.Column(content_controls, spacing=12, scroll=ft.ScrollMode.ADAPTIVE),
                        width=420,
                        height=650
                    ),
                    actions=[
                        ft.TextButton("Close", on_click=lambda e: close_dialog())
                    ],
                    shape=ft.RoundedRectangleBorder(radius=16)
                )
                page.dialog.open = True
                page.update()
            except Exception as e:
                logger.error(f"Error opening report detail: {e}")
                show_snack("Error loading report details", "#ef4444")

        def close_dialog(e=None):
            page.dialog.open = False
            page.update()

        def logout(e=None):
            current_user["id"] = None
            current_user["username"] = None
            current_user["role"] = None
            login_screen()

        stats_cards_container.content = create_stats_cards()
        load_my_reports()

        header = ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(f"Welcome back, {current_user['username']}! 👋", size=20, weight=ft.FontWeight.BOLD, color="#1e293b"),
                    ft.Text("Community Issue Reporting", size=14, color="#64748b"),
                ], expand=True),
                ft.IconButton(
                    icon=ft.Icons.LOGOUT,
                    on_click=logout,
                    icon_color="#64748b",
                    tooltip="Logout"
                )
            ]),
            padding=20,
            bgcolor="white",
            border_radius=16,
            margin=ft.margin.only(bottom=10)
        )

        page.add(
            ft.Column([
                header,
                ft.Container(height=10),
                stats_cards_container,
                ft.Container(height=10),
                ft.Row([
                    ft.Text("My Reports", size=18, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        on_click=lambda e: load_my_reports(),
                        icon_color="#64748b",
                        tooltip="Refresh"
                    )
                ]),
                ft.Container(height=10),
                ft.Container(
                    content=reports_list,
                    expand=True
                ),
                ft.Container(
                    content=primary_button("Report New Issue", lambda e: report_issue_screen(), icon=ft.Icons.ADD),
                    padding=20
                )
            ], expand=True)
        )

    def report_issue_screen():
        page.clean()

        # Reset photo state when entering report screen
        photo_state.photo_data = None
        photo_state.photo_name = None

        name = modern_textfield(
            label="Your Name",
            prefix_icon=ft.Icons.PERSON,
            hint_text="Enter your full name"
        )
        problem_type = ft.Dropdown(
            label="Problem Type",
            options=[
                ft.dropdown.Option("🚗 Traffic - Traffic congestion or road blockage"),
                ft.dropdown.Option("🗑️ Waste - Garbage accumulation or improper disposal"),
                ft.dropdown.Option("💧 Water - Water supply issues or leaks"),
                ft.dropdown.Option("⚡ Power - Electricity outage or power issues"),
                ft.dropdown.Option("🛣️ Road - Potholes or road damage"),
                ft.dropdown.Option("🌳 Environment - Parks, trees, or public spaces"),
                ft.dropdown.Option("🏢 Public Facility - Government buildings or services"),
                ft.dropdown.Option("🚨 Emergency - Urgent public safety issue"),
                ft.dropdown.Option("📝 Other - Other community issues"),
            ],
            border_radius=12,
            border_color="#e2e8f0",
            focused_border_color="#2563eb"
        )
        location = modern_textfield(
            label="Location",
            prefix_icon=ft.Icons.LOCATION_ON,
            hint_text="Enter the exact location"
        )
        issue = modern_textfield(
            label="Issue Description",
            multiline=True,
            min_lines=3,
            max_lines=5,
            prefix_icon=ft.Icons.DESCRIPTION,
            hint_text="Describe the issue in detail..."
        )
        date = modern_textfield(
            label="Date of Issue",
            prefix_icon=ft.Icons.CALENDAR_TODAY,
            hint_text="YYYY-MM-DD or 'Today'"
        )
        priority = ft.Dropdown(
            label="Priority Level",
            options=[
                ft.dropdown.Option("🟢 Low - Minor issue, no immediate action needed"),
                ft.dropdown.Option("🟡 Medium - Needs attention within a few days"),
                ft.dropdown.Option("🔴 High - Requires immediate attention"),
                ft.dropdown.Option("🚨 Emergency - Critical issue needing urgent action"),
            ],
            border_radius=12,
            border_color="#e2e8f0",
            focused_border_color="#2563eb"
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
            if not all([name.value, problem_type.value, location.value, issue.value, date.value, priority.value]):
                show_snack("Please fill in all required fields!", "#f59e0b")
                return

            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Clean the problem type and priority (remove emoji and description)
                clean_problem_type = problem_type.value.split(" ", 1)[-1] if " " in problem_type.value else problem_type.value
                clean_priority = priority.value.split(" ", 1)[0] if " " in priority.value else priority.value

                cursor.execute("""
                    INSERT INTO reports (user_id, name, problem_type, location, issue, date, priority, photo_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    current_user["id"],
                    name.value,
                    clean_problem_type,
                    location.value,
                    issue.value,
                    date.value,
                    clean_priority,
                    photo_state.photo_data
                ))

                conn.commit()
                cursor.close()
                conn.close()

                show_snack("Report submitted successfully! 🎉")
                user_dashboard_screen()

            except Exception as e:
                logger.error(f"Error submitting report: {e}")
                show_snack("Error submitting report. Please try again.", "#ef4444")

        def go_back(e):
            user_dashboard_screen()

        report_content = ft.Column([
            ft.Row([
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    on_click=go_back,
                    icon_color="#64748b"
                ),
                ft.Text("Report Community Issue", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
            ]),
            ft.Container(height=20),
            name,
            problem_type,
            location,
            issue,
            date,
            priority,
            ft.Container(height=10),
            ft.Text("Add Photo (Optional)", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
            ft.Text("Take a photo or upload from gallery", size=14, color="#64748b"),
            ft.Container(height=10),
            ft.Row([
                secondary_button("Take Photo", open_camera_picker, icon=ft.Icons.CAMERA_ALT),
                secondary_button("Upload Photo", open_file_picker, icon=ft.Icons.PHOTO_LIBRARY),
            ]),
            ft.Container(height=10),
            ft.Stack([
                photo_display,
                photo_preview
            ]),
            ft.Container(height=20),
            primary_button("Submit Report", submit_report, icon=ft.Icons.SEND),
        ], spacing=12)

        page.add(
            ft.Container(
                content=modern_card(report_content, padding=25),
                padding=20
            )
        )

        # Initialize photo display
        update_photo_display()

    def logout():
        current_user["id"] = None
        current_user["username"] = None
        current_user["role"] = None
        login_screen()

    # Start with login screen
    login_screen()

# Run the app
if __name__ == "__main__":
    ft.app(target=main)
