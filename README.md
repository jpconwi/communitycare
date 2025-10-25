# CommunityCare - Community Reporting System

A web-based application for reporting and managing community issues.

## Features

- 📱 Responsive web design
- 📸 Photo upload and camera capture
- 👥 User registration and authentication
- 🛠️ Admin dashboard for report management
- 🔔 Real-time notifications
- 📊 Report statistics and analytics

## Deployment

### Deploy on Render

1. Fork this repository
2. Create a new Web Service on Render
3. Connect your GitHub repository
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `python app.py`
6. Add environment variable `DATABASE_URL` with your PostgreSQL connection string

### Local Development

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up PostgreSQL database
4. Run: `python app.py`

## Demo Accounts

- **Admin**: admin@community.com / admin123
- **User**: Register a new account

## Technology Stack

- **Backend**: Python, Flet
- **Database**: PostgreSQL
- **Deployment**: Render
- **Frontend**: Flutter (compiled to web via Flet)