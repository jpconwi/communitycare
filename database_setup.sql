-- CommunityCare Database Setup for PostgreSQL
-- Run this in DBeaver with your local connection

-- Enable UUID extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop tables if they exist (optional - remove if you want to keep existing data)
DROP TABLE IF EXISTS admin_logs CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS reports CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Create users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create reports table
CREATE TABLE reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    problem_type VARCHAR(100) NOT NULL,
    location TEXT NOT NULL,
    issue TEXT NOT NULL,
    date VARCHAR(50) NOT NULL,
    status VARCHAR(20) DEFAULT 'Pending',
    priority VARCHAR(20) DEFAULT 'Medium',
    photo_data TEXT,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create notifications table
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    report_id INTEGER REFERENCES reports(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    type VARCHAR(50) DEFAULT 'status_update',
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create admin_logs table
CREATE TABLE admin_logs (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id INTEGER,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX idx_reports_user_id ON reports(user_id);
CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_created_at ON reports(created_at);
CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_is_read ON notifications(is_read);
CREATE INDEX idx_admin_logs_admin_id ON admin_logs(admin_id);

-- Insert admin user
INSERT INTO users (username, password, email, role) 
VALUES ('admin', 'admin123', 'admin@community.com', 'admin')
ON CONFLICT (email) DO NOTHING;

-- Insert sample user for testing
INSERT INTO users (username, password, email, phone, role) 
VALUES ('john_doe', 'password123', 'john@example.com', '+1234567890', 'user')
ON CONFLICT (email) DO NOTHING;

-- Insert sample reports
INSERT INTO reports (user_id, name, problem_type, location, issue, date, status, priority) VALUES
(1, 'Admin User', '🚧 Infrastructure', 'Main Street Downtown', 'Pothole causing traffic issues', '2024-01-15 10:30', 'Pending', 'High'),
(2, 'John Doe', '🧹 Sanitation', 'Central Park', 'Garbage accumulation near benches', '2024-01-14 14:20', 'In Progress', 'Medium'),
(1, 'Admin User', '🛡️ Safety', 'School Zone Area', 'Broken street light making area unsafe at night', '2024-01-13 18:45', 'Resolved', 'Emergency')
ON CONFLICT DO NOTHING;

-- Display confirmation
SELECT '✅ Database setup completed successfully!' as message;

-- Show created tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;