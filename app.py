import os
import flet as ft
import psycopg2
from datetime import datetime
import re
import base64
import io
from PIL import Image
import logging

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

# ... rest of your app code ...

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

# ... rest of your app code continues here ...

# ... rest of your app.py code remains the same ...

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

    page.assets_dir = "static"
    page.update()

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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=FALSE", (current_user["id"],))
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return count
        return 0

    def add_notification(user_id, report_id, message, notification_type="status_update"):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notifications (user_id, report_id, message, type) VALUES (%s, %s, %s, %s)",
            (user_id, report_id, message, notification_type)
        )
        conn.commit()
        cursor.close()
        conn.close()

    def add_admin_log(action, target_type, target_id=None, details=None):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admin_logs (admin_id, action, target_type, target_id, details) VALUES (%s, %s, %s, %s, %s)",
            (current_user["id"], action, target_type, target_id, details)
        )
        conn.commit()
        cursor.close()
        conn.close()

    def get_report_stats():
        stats = {}
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
        
        cursor.execute("SELECT COUNT(*) FROM reports WHERE user_id=%s", (current_user["id"],))
        stats['my_reports'] = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
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
            image.save(buffered, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
        except Exception as e:
            logging.error(f"Error compressing image: {e}")
            return image_data

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
                show_snack("Invalid email or password!", "#ef4444")

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
                show_snack("Username already exists!", "#ef4444")

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

                        def create_status_handler(rid=r[0], status="In Progress"):
                            return lambda e: update_report_status(rid, status)

                        def create_resolved_handler(rid=r[0]):
                            return lambda e: update_report_status(rid, "Resolved")

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
                                            on_click=create_status_handler()
                                        ),
                                        ft.PopupMenuItem(
                                            text="Mark Resolved",
                                            on_click=create_resolved_handler()
                                        ),
                                        ft.PopupMenuItem(
                                            text="Delete",
                                            on_click=create_delete_handler()
                                        ),
                                    ]
                                ),
                            )
                        )
                page.update()

            def update_report_status(report_id, new_status):
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

            def delete_report(report_id):
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

            def open_report_detail(item):
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

                # Create helper functions for button actions
                def mark_in_progress_and_close():
                    update_report_status(report_id, "In Progress")
                    close_dialog()

                def mark_resolved_and_close():
                    update_report_status(report_id, "Resolved")
                    close_dialog()

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
                                ft.Text(created_at[:16] if created_at else "N/A", size=14, color="#1e293b",
                                        expand=True),
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
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.PHOTO_CAMERA, size=20, color="#2563eb"),
                                    ft.Text("Attached Photo", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                                ]),
                                ft.Container(height=8),

                                ft.Container(
                                    content=ft.Column([
                                        ft.Container(
                                            content=ft.Image(
                                                src_base64=photo_data,
                                                width=380,
                                                height=280,
                                                fit=ft.ImageFit.CONTAIN,
                                                border_radius=12,
                                                repeat=ft.ImageRepeat.NO_REPEAT,
                                                gapless_playback=True,
                                            ),
                                            border=ft.border.all(2, "#e2e8f0"),
                                            border_radius=12,
                                            padding=2,
                                            bgcolor="white",
                                            shadow=ft.BoxShadow(
                                                spread_radius=1,
                                                blur_radius=10,
                                                color=ft.Colors.BLACK12,
                                                offset=ft.Offset(0, 2)
                                            )
                                        ),
                                        ft.Container(height=8),
                                        ft.Row([
                                            ft.Icon(ft.Icons.INFO_OUTLINED, size=14, color="#64748b"),
                                            ft.Text("Photo provided by reporter", size=12, color="#64748b"),
                                        ], alignment=ft.MainAxisAlignment.CENTER),
                                    ], spacing=0),
                                    alignment=ft.alignment.center,
                                )
                            ], spacing=0),
                            padding=15,
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
                            lambda e: mark_in_progress_and_close(),
                            icon=ft.Icons.UPDATE
                        ),
                        secondary_button(
                            "Mark Resolved",
                            lambda e: mark_resolved_and_close(),
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

            def show_delete_dialog(report_id):
                def confirm_delete(e):
                    delete_report(report_id)
                    page.dialog.open = False
                    page.update()

                page.dialog = ft.AlertDialog(
                    title=ft.Text("Confirm Delete"),
                    content=ft.Text("Are you sure you want to delete this report? This action cannot be undone."),
                    actions=[
                        ft.TextButton("Delete", on_click=confirm_delete, style=ft.ButtonStyle(color=ft.Colors.RED)),
                        ft.TextButton("Cancel", on_click=lambda e: setattr(page.dialog, "open", False))
                    ]
                )
                page.dialog.open = True
                page.update()

            def close_dialog():
                page.dialog.open = False
                page.update()

            load_community_reports()

            return ft.Column([
                ft.Text("Community Reports Management", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Manage all community reports", size=14, color=ft.Colors.GREY_600),
                ft.Container(
                    content=reports_list,
                    height=400
                ),
                ft.FilledButton("Refresh All", icon=ft.Icons.REFRESH,
                                on_click=lambda e: [load_community_reports(), refresh_stats()]),
            ], spacing=12)

        def create_user_management_tab():
            users_list = ft.ListView(expand=True, spacing=6)

            def load_users():
                users_list.controls.clear()
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, username, email, phone, role, created_at FROM users ORDER BY created_at DESC")
                users = cursor.fetchall()
                cursor.close()
                conn.close()

                for user in users:
                    def create_role_handler(uid=user[0], current_role=user[4]):
                        return lambda e: toggle_user_role(uid, current_role)

                    def create_delete_handler(uid=user[0]):
                        return lambda e: delete_user(uid)

                    menu_items = []

                    if user[0] != current_user["id"]:
                        menu_items.extend([
                            ft.PopupMenuItem(
                                text="Make Admin" if user[4] == "user" else "Make User",
                                on_click=create_role_handler()
                            ),
                            ft.PopupMenuItem(
                                text="Delete",
                                on_click=create_delete_handler()
                            )
                        ])
                    else:
                        menu_items.append(
                            ft.PopupMenuItem(text="Current User", disabled=True)
                        )

                    users_list.controls.append(
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.PERSON, color=ft.Colors.BLUE_500),
                            title=ft.Text(user[1], weight=ft.FontWeight.W_600),
                            subtitle=ft.Text(f"{user[2]} • {user[4]}"),
                            trailing=ft.PopupMenuButton(
                                icon=ft.Icons.MORE_VERT,
                                items=menu_items
                            ),
                        )
                    )
                page.update()

            def toggle_user_role(user_id, current_role):
                conn = get_db_connection()
                cursor = conn.cursor()
                new_role = "admin" if current_role == "user" else "user"
                cursor.execute("UPDATE users SET role=%s WHERE id=%s", (new_role, user_id))
                conn.commit()
                cursor.close()
                conn.close()
                add_admin_log("UPDATE_ROLE", "user", user_id, f"Role changed to {new_role}")
                show_snack(f"User role updated to {new_role}")
                load_users()

            def delete_user(user_id):
                def confirm_delete(e):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
                    user = cursor.fetchone()

                    cursor.execute("DELETE FROM reports WHERE user_id=%s", (user_id,))
                    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
                    conn.commit()
                    cursor.close()
                    conn.close()

                    if user:
                        add_admin_log("DELETE", "user", user_id, f"Deleted user: {user[0]} and all their reports")
                    show_snack("User and all their reports deleted successfully")
                    load_users()
                    refresh_stats()
                    page.dialog.open = False
                    page.update()

                page.dialog = ft.AlertDialog(
                    title=ft.Text("Confirm Delete"),
                    content=ft.Text(
                        "Are you sure you want to delete this user? All their reports will also be deleted."),
                    actions=[
                        ft.TextButton("Delete", on_click=confirm_delete, style=ft.ButtonStyle(color=ft.Colors.RED)),
                        ft.TextButton("Cancel", on_click=lambda e: setattr(page.dialog, "open", False))
                    ]
                )
                page.dialog.open = True
                page.update()

            load_users()

            return ft.Column([
                ft.Text("User Management", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Manage user accounts and permissions", size=14, color=ft.Colors.GREY_600),
                ft.Container(
                    content=users_list,
                    height=400
                ),
                ft.FilledButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: load_users()),
            ], spacing=12)

        def create_activity_log_tab():
            logs_list = ft.ListView(expand=True, spacing=6)

            def load_logs():
                logs_list.controls.clear()
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT al.id, u.username, al.action, al.target_type, al.target_id, al.details, al.created_at
                    FROM admin_logs al JOIN users u ON al.admin_id = u.id ORDER BY al.created_at DESC LIMIT 100
                """)
                logs = cursor.fetchall()
                cursor.close()
                conn.close()

                if not logs:
                    logs_list.controls.append(ft.Text("No activity logs yet.", color=ft.Colors.GREY_600))
                else:
                    for log in logs:
                        icon_color = {
                            "DELETE": ft.Colors.RED,
                            "UPDATE_STATUS": ft.Colors.BLUE,
                            "UPDATE_ROLE": ft.Colors.ORANGE
                        }.get(log[2], ft.Colors.GREEN)

                        logs_list.controls.append(
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.HISTORY, color=icon_color),
                                title=ft.Text(log[2], weight=ft.FontWeight.W_600, color=icon_color),
                                subtitle=ft.Text(f"By {log[1]} • {log[3]} #{log[4] if log[4] else 'N/A'}"),
                                trailing=ft.Text(log[6][:16], size=12, color=ft.Colors.GREY_600),
                            )
                        )
                page.update()

            def clear_logs():
                def confirm_clear(e):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM admin_logs")
                    conn.commit()
                    cursor.close()
                    conn.close()
                    show_snack("Activity logs cleared")
                    load_logs()
                    page.dialog.open = False
                    page.update()

                page.dialog = ft.AlertDialog(
                    title=ft.Text("Clear All Logs"),
                    content=ft.Text("Are you sure you want to clear all activity logs?"),
                    actions=[
                        ft.TextButton("Clear All", on_click=confirm_clear, style=ft.ButtonStyle(color=ft.Colors.RED)),
                        ft.TextButton("Cancel", on_click=lambda e: setattr(page.dialog, "open", False))
                    ]
                )
                page.dialog.open = True
                page.update()

            load_logs()

            return ft.Column([
                ft.Row([
                    ft.Text("Admin Activity Log", size=16, weight=ft.FontWeight.BOLD, expand=True),
                    ft.FilledTonalButton("Clear Logs", icon=ft.Icons.CLEAR, on_click=lambda e: clear_logs()),
                ]),
                ft.Text("Recent admin activities and actions", size=14, color=ft.Colors.GREY_600),
                ft.Container(
                    content=logs_list,
                    height=400
                ),
                ft.FilledButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: load_logs()),
            ], spacing=12)

        def update_admin_content():
            content_area.controls.clear()
            if current_admin_tab == 0:
                content_area.controls.append(create_community_reports_tab())
            elif current_admin_tab == 1:
                content_area.controls.append(create_user_management_tab())
            elif current_admin_tab == 2:
                content_area.controls.append(create_activity_log_tab())
            page.update()

        content_area = ft.Column(scroll=ft.ScrollMode.AUTO)

        stats_cards_container.content = create_stats_cards()

        update_admin_content()

        def logout_user():
            add_admin_log("LOGOUT", "system", None, "Admin user logged out")
            current_user["id"] = None
            current_user["username"] = None
            current_user["role"] = None
            show_snack("Logged out successfully")
            login_screen()

        # Create header with logout button
        header_row = ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS, color=ft.Colors.BLUE_700),
                ft.Text("Admin Dashboard", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
            ]),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.LOGOUT,
                icon_color=ft.Colors.RED_500,
                tooltip="Logout",
                on_click=lambda e: logout_user(),
                style=ft.ButtonStyle(
                    color=ft.Colors.RED_500,
                    side=ft.BorderSide(1, ft.Colors.RED_500)
                )
            )
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        admin_content = ft.Column([
            ft.Container(height=8),
            ft.Card(content=ft.Container(padding=20, content=ft.Column([
                header_row,
                stats_cards_container,
                ft.Divider(),
                admin_tabs,
                content_area,
                ft.Container(height=20),

                ft.Row([
                    ft.OutlinedButton(
                        text="Logout",
                        icon=ft.Icons.LOGOUT,
                        on_click=lambda e: logout_user(),
                        style=ft.ButtonStyle(
                            color="#ef4444",
                            side=ft.BorderSide(1, "#ef4444")
                        ),
                        width=200
                    )
                ], alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=12))),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        page.add(
            ft.Container(
                content=admin_content,
                padding=10,
                expand=True
            )
        )

    def user_dashboard_screen():
        page.clean()

        class PhotoState:
            def __init__(self):
                self.photo_data = None
                self.photo_name = None

        photo_state = PhotoState()

        problem_type = ft.Dropdown(
            label="Problem Type*",
            width=280,
            options=[
                ft.dropdown.Option("🚧 Infrastructure"),
                ft.dropdown.Option("🧹 Sanitation"),
                ft.dropdown.Option("🛡️ Safety"),
                ft.dropdown.Option("🌳 Environment"),
                ft.dropdown.Option("🔊 Noise"),
                ft.dropdown.Option("❓ Other")
            ],
            border_radius=12,
            border_color="#e2e8f0",
            focused_border_color="#2563eb"
        )

        location = modern_textfield(
            label="Location*",
            width=280,
            hint_text="Enter exact location",
            prefix_icon=ft.Icons.LOCATION_ON
        )

        issue = modern_textfield(
            label="Description*",
            multiline=True,
            min_lines=3,
            width=280,
            hint_text="Describe the problem in detail..."
        )

        priority = ft.Dropdown(
            label="Priority Level",
            width=280,
            options=[
                ft.dropdown.Option("🟢 Low"),
                ft.dropdown.Option("🟡 Medium"),
                ft.dropdown.Option("🔴 High"),
                ft.dropdown.Option("🚨 Emergency")
            ],
            value="🟡 Medium",
            border_radius=12,
            border_color="#e2e8f0",
            focused_border_color="#2563eb"
        )

        uploaded_images = ft.Row(spacing=8, wrap=True, controls=[])
        photo_name_text = ft.Text("", size=12, color="#64748b")

        def handle_file_upload(e: ft.FilePickerResultEvent):
            if e.files and e.files[0]:
                try:
                    with open(e.files[0].path, "rb") as img_file:
                        photo_data = base64.b64encode(img_file.read()).decode('utf-8')
                    
                    # Compress the image
                    compressed_data = compress_image(photo_data)
                    
                    photo_state.photo_data = compressed_data
                    photo_state.photo_name = e.files[0].name
                    update_photo_display()
                    show_snack("Photo uploaded successfully! 📸")
                except Exception as ex:
                    show_snack(f"Error uploading photo: {str(ex)}", "#ef4444")

        def handle_camera_photo(e: ft.FilePickerResultEvent):
            if e.files and e.files[0]:
                try:
                    with open(e.files[0].path, "rb") as img_file:
                        photo_data = base64.b64encode(img_file.read()).decode('utf-8')
                    
                    # Compress the image
                    compressed_data = compress_image(photo_data)
                    
                    photo_state.photo_data = compressed_data
                    photo_state.photo_name = "camera_photo.jpg"
                    update_photo_display()
                    show_snack("Photo captured successfully! 📸")
                except Exception as ex:
                    show_snack(f"Error processing photo: {str(ex)}", "#ef4444")

        file_picker = ft.FilePicker(on_result=handle_file_upload)
        camera_picker = ft.FilePicker(on_result=handle_camera_photo)
        page.overlay.extend([file_picker, camera_picker])

        def update_photo_display():
            uploaded_images.controls.clear()
            if photo_state.photo_data:
                uploaded_images.controls.append(
                    ft.Container(
                        width=80,
                        height=80,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        border_radius=12,
                        content=ft.Image(
                            src_base64=photo_state.photo_data,
                            fit=ft.ImageFit.COVER,
                            border_radius=12
                        ),
                        shadow=ft.BoxShadow(
                            spread_radius=1,
                            blur_radius=8,
                            color=ft.Colors.BLACK12
                        )
                    )
                )
                photo_name_text.value = f"📷 {photo_state.photo_name}"
            else:
                photo_name_text.value = ""
            page.update()

        def clear_photo(e):
            photo_state.photo_data = None
            photo_state.photo_name = None
            update_photo_display()
            show_snack("Photo removed", "#f59e0b")

        def open_camera(e):
            camera_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["png", "jpg", "jpeg"],
                file_type=ft.FilePickerFileType.IMAGE
            )

        my_list = ft.ListView(expand=True, spacing=8)

        def load_user_reports():
            my_list.controls.clear()
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, problem_type, location, issue, date, status, priority, photo_data 
                FROM reports WHERE user_id=%s ORDER BY id DESC
            """, (current_user["id"],))
            data = cursor.fetchall()
            cursor.close()
            conn.close()

            if not data:
                my_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.DESCRIPTION, size=48, color="#cbd5e1"),
                            ft.Text("No reports yet", size=16, color="#64748b"),
                            ft.Text("Submit your first community issue report", size=14, color="#94a3b8"),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        padding=40,
                        alignment=ft.alignment.center
                    )
                )
            else:
                for r in data:
                    clean_problem_type = r[1].split(" ", 1)[-1] if " " in r[1] else r[1]

                    my_list.controls.append(
                        modern_card(
                            ft.Column([
                                ft.Row([
                                    ft.Text(f"#{r[0]}", size=12, color="#64748b", weight=ft.FontWeight.W_500),
                                    status_badge(r[5]),
                                    priority_badge(
                                        r[6].replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").replace("🚨 ", ""))
                                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                ft.Text(clean_problem_type, size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                                ft.Text(r[2], size=14, color="#64748b"),
                                ft.Text(r[4][:16], size=12, color="#94a3b8"),
                                ft.Row([
                                    secondary_button(
                                        "View Details",
                                        lambda e, item=r: open_report_detail(item),
                                        icon=ft.Icons.VISIBILITY
                                    ),
                                ])
                            ], spacing=8)
                        )
                    )
            page.update()

        def open_report_detail(item):
            clean_problem_type = item[1].split(" ", 1)[-1] if " " in item[1] else item[1]

            content_controls = [
                ft.Row([
                    ft.Text(f"Report #{item[0]}", size=18, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                    status_badge(item[5]),
                ]),
                ft.Container(height=10),
                ft.Row([
                    ft.Icon(ft.Icons.CATEGORY, size=16, color="#64748b"),
                    ft.Text("Type:", size=14, color="#64748b", width=60),
                    ft.Text(clean_problem_type, size=14, color="#1e293b", expand=True),
                ]),
                ft.Row([
                    ft.Icon(ft.Icons.LOCATION_ON, size=16, color="#64748b"),
                    ft.Text("Location:", size=14, color="#64748b", width=60),
                    ft.Text(item[2], size=14, color="#1e293b", expand=True),
                ]),
                ft.Row([
                    ft.Icon(ft.Icons.FLAG, size=16, color="#64748b"),
                    ft.Text("Priority:", size=14, color="#64748b", width=60),
                    priority_badge(item[6].replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").replace("🚨 ", "")),
                ]),
                ft.Row([
                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=16, color="#64748b"),
                    ft.Text("Date:", size=14, color="#64748b", width=60),
                    ft.Text(item[4], size=14, color="#1e293b", expand=True),
                ]),
                ft.Container(height=10),
                ft.Text("Description:", size=14, weight=ft.FontWeight.W_600, color="#1e293b"),
                ft.Text(item[3], size=14, color="#475569"),
            ]

            if item[7]:
                content_controls.extend([
                    ft.Container(height=10),
                    ft.Text("Attached Photo:", size=14, weight=ft.FontWeight.W_600, color="#1e293b"),
                    ft.Container(
                        width=300,
                        height=200,
                        content=ft.Image(
                            src_base64=item[7],
                            fit=ft.ImageFit.COVER,
                            border_radius=12
                        ),
                        border_radius=12,
                        shadow=ft.BoxShadow(
                            spread_radius=1,
                            blur_radius=8,
                            color=ft.Colors.BLACK12
                        )
                    )
                ])

            page.dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Report Details"),
                content=ft.Container(
                    content=ft.Column(content_controls, spacing=8),
                    width=350
                ),
                actions=[
                    secondary_button("Close", lambda e: close_dialog())
                ],
                shape=ft.RoundedRectangleBorder(radius=16)
            )
            page.dialog.open = True
            page.update()

        def close_dialog():
            page.dialog.open = False
            page.update()

        def submit_report(e):
            if not all([problem_type.value, location.value, issue.value]):
                show_snack("Please fill in all required fields! 📝", "#f59e0b")
                return

            date = datetime.now().strftime("%Y-%m-%d %H:%M")

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reports (user_id, name, problem_type, location, issue, date, priority, photo_data, latitude, longitude) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (current_user["id"], current_user["username"], problem_type.value, location.value,
                  issue.value, date, priority.value, photo_state.photo_data, "", ""))
            conn.commit()
            cursor.close()
            conn.close()

            problem_type.value = ""
            location.value = ""
            issue.value = ""
            priority.value = "🟡 Medium"
            clear_photo(None)

            show_snack("Report submitted successfully! ✅")
            load_user_reports()

        def show_my_reports():
            load_user_reports()
            page.clean()
            page.add(
                ft.Container(
                    content=ft.Column([
                        ft.Container(
                            content=ft.Row([
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    on_click=lambda e: user_dashboard_screen(),
                                    icon_color="#64748b"
                                ),
                                ft.Text("My Reports", size=20, weight=ft.FontWeight.BOLD, color="#1e293b", expand=True),
                                ft.Icon(ft.Icons.DESCRIPTION, color="#2563eb"),
                            ]),
                            padding=20
                        ),
                        ft.Container(
                            content=my_list,
                            padding=20,
                            expand=True
                        )
                    ]),
                    expand=True
                )
            )

        def show_notifications():
            notifications_list = ft.ListView(expand=True, spacing=8)

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT n.message, n.created_at, r.problem_type 
                FROM notifications n 
                LEFT JOIN reports r ON n.report_id = r.id 
                WHERE n.user_id=%s 
                ORDER BY n.created_at DESC
            """, (current_user["id"],))
            notifications = cursor.fetchall()
            cursor.close()
            conn.close()

            if not notifications:
                notifications_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.NOTIFICATIONS_NONE, size=48, color="#cbd5e1"),
                            ft.Text("No notifications", size=16, color="#64748b"),
                            ft.Text("You're all caught up! 🎉", size=14, color="#94a3b8"),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        padding=40,
                        alignment=ft.alignment.center
                    )
                )
            else:
                for notification in notifications:
                    notifications_list.controls.append(
                        modern_card(
                            ft.Column([
                                ft.Text(notification[0], size=14, color="#1e293b"),
                                ft.Text(notification[1][:16], size=12, color="#64748b"),
                            ], spacing=4)
                        )
                    )

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE notifications SET is_read=TRUE WHERE user_id=%s", (current_user["id"],))
                conn.commit()
                cursor.close()
                conn.close()

            page.clean()
            page.add(
                ft.Container(
                    content=ft.Column([
                        ft.Container(
                            content=ft.Row([
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    on_click=lambda e: user_dashboard_screen(),
                                    icon_color="#64748b"
                                ),
                                ft.Text("Notifications", size=20, weight=ft.FontWeight.BOLD, color="#1e293b",
                                        expand=True),
                                ft.Icon(ft.Icons.NOTIFICATIONS, color="#2563eb"),
                            ]),
                            padding=20
                        ),
                        ft.Container(
                            content=notifications_list,
                            padding=20,
                            expand=True
                        )
                    ]),
                    expand=True
                )
            )

        def logout_user():
            current_user["id"] = None
            current_user["username"] = None
            current_user["role"] = None
            show_snack("See you soon! 👋")
            login_screen()

        load_user_reports()

        notification_count = get_notifications_count()
        notification_button = ft.IconButton(
            icon=ft.Icons.NOTIFICATIONS_OUTLINED,
            icon_size=24,
            on_click=lambda e: show_notifications(),
            icon_color="#64748b",
        )

        if notification_count > 0:
            notification_button.badge = ft.Container(
                content=ft.Text(str(notification_count), color="white", size=10, weight=ft.FontWeight.BOLD),
                bgcolor="#ef4444",
                border_radius=20,
                padding=ft.padding.symmetric(horizontal=6, vertical=2),
                right=2,
                top=2
            )

        dashboard_content = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            controls=[
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"Hello, {current_user['username']}! 👋",
                                    size=20, weight=ft.FontWeight.BOLD, color="#1e293b"),
                            ft.Text("Report community issues", size=14, color="#64748b"),
                        ], expand=True),
                        notification_button,
                    ]),
                    padding=20
                ),

                ft.Container(
                    content=modern_card(
                        ft.Row([
                            ft.Column([
                                ft.Text("Your Reports", size=12, color="#64748b"),
                                ft.Text(str(len(my_list.controls) if my_list.controls else "0"),
                                        size=24, weight=ft.FontWeight.BOLD, color="#2563eb"),
                            ], expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.VerticalDivider(width=1, color="#e2e8f0"),
                            ft.Column([
                                ft.Text("Pending", size=12, color="#64748b"),
                                ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color="#f59e0b"),
                            ], expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ]),
                        padding=20
                    )
                ),

                modern_card(
                    ft.Column([
                        ft.Text("New Report", size=18, weight=ft.FontWeight.BOLD, color="#1e293b"),
                        ft.Container(height=10),
                        problem_type,
                        location,
                        issue,
                        priority,
                        ft.Container(height=10),
                        ft.Row([
                            secondary_button(
                                "Upload Photo",
                                lambda _: file_picker.pick_files(
                                    allow_multiple=False,
                                    allowed_extensions=["png", "jpg", "jpeg"]
                                ),
                                icon=ft.Icons.UPLOAD_FILE
                            ),
                            secondary_button(
                                "Take Photo",
                                open_camera,
                                icon=ft.Icons.CAMERA_ALT
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.TextButton(
                            "Clear Photo",
                            on_click=clear_photo,
                            style=ft.ButtonStyle(color="#64748b")
                        ) if photo_state.photo_data else ft.Container(),
                        uploaded_images,
                        photo_name_text,
                        ft.Container(height=10),
                        primary_button("Submit Report", submit_report, icon=ft.Icons.SEND),
                    ], spacing=12),
                    padding=25
                ),

                modern_card(
                    ft.Column([
                        ft.Text("Quick Actions", size=16, weight=ft.FontWeight.W_600, color="#1e293b"),
                        ft.Container(height=10),
                        ft.Row([
                            secondary_button(
                                "My Reports",
                                lambda e: show_my_reports(),
                                icon=ft.Icons.LIST_ALT,
                                width=120
                            ),
                            secondary_button(
                                "Notifications",
                                lambda e: show_notifications(),
                                icon=ft.Icons.NOTIFICATIONS,
                                width=120
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Container(height=10),
                        ft.Row([
                            ft.OutlinedButton(
                                text="Logout",
                                icon=ft.Icons.LOGOUT,
                                on_click=lambda e: logout_user(),
                                style=ft.ButtonStyle(
                                    color="#ef4444",
                                    side=ft.BorderSide(1, "#ef4444")
                                ),
                                width=260
                            )
                        ], alignment=ft.MainAxisAlignment.CENTER)
                    ], spacing=12),
                    padding=20,
                ),

                ft.Container(height=20),
            ],
            spacing=0
        )

        page.add(
            ft.Container(
                content=dashboard_content,
                padding=0,
                expand=True
            )
        )

    login_screen()

if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER, port=8501)