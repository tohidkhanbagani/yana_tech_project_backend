from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

# ==========================================
#              MASTER DATA
# ==========================================

class Departments_Roles(Base):
    __tablename__ = "departments_roles"
    id = Column(String, primary_key=True, default=generate_uuid)
    department_name = Column(String, nullable=False) # e.g., 'IT', 'Social Media', 'Design'
    role_name = Column(String, nullable=False)       # e.g., 'Java Developer', 'Video Editor'
    is_active = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ==========================================
#          USERS & AUTHENTICATION
# ==========================================

class Admins(Base):
    """Dedicated table for system administrators to isolate them from the employee hierarchy."""
    __tablename__ = "admins"
    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    email = Column(String, nullable=True, default="N/A")
    full_name = Column(String, nullable=True, default="N/A")
    access_level = Column(String, nullable=True, default="SystemAdmin")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Employees(Base):
    """Unified table for all staff, containing credentials, HR data, and financial profiles."""
    __tablename__ = "employees"
    id = Column(String, primary_key=True, default=generate_uuid)
    
    # Credentials & Access
    username = Column(String, unique=True, nullable=True)
    password = Column(String, nullable=True)
    role_id = Column(String, ForeignKey("departments_roles.id"), nullable=True)
    is_active = Column(Boolean, nullable=True, default=True)
    
    # Basic HR Data
    full_name = Column(String, nullable=True, default="N/A")
    fathers_name = Column(String, nullable=True, default="N/A")
    date_of_birth = Column(String, nullable=True, default="N/A")
    gender = Column(String, nullable=True, default="N/A")
    contact_number = Column(String, nullable=True, default="N/A")
    alternate_contact = Column(String, nullable=True, default="N/A")
    address = Column(String, nullable=True, default="N/A")
    email = Column(String, nullable=True, default="N/A")
    alternate_email = Column(String, nullable=True, default="N/A")
    
    # Financial & Auto-Calculation Metrics
    hourly_cost_rate = Column(Float, nullable=True, default=0.0)
    hourly_billing_rate = Column(Float, nullable=True, default=0.0)
    salary = Column(Float, nullable=True, default=0.0)
    
    # Compliance & Docs
    adhar_number = Column(String, nullable=True, default="N/A")
    adhar_front = Column(String, nullable=True, default="N/A")
    adhar_back = Column(String, nullable=True, default="N/A")
    pan_number = Column(String, nullable=True, default="N/A")
    pan_front = Column(String, nullable=True, default="N/A")
    pan_back = Column(String, nullable=True, default="N/A")
    
    # Professional Profile
    date_of_joining = Column(String, nullable=True, default="N/A")
    reporting_manager = Column(String, nullable=True, default="N/A")
    highest_qualification = Column(String, nullable=True, default="N/A")
    specialization = Column(String, nullable=True, default="N/A")
    experience = Column(String, nullable=True, default="N/A")
    previous_employer = Column(String, nullable=True, default="N/A")
    previous_job_role = Column(String, nullable=True, default="N/A")
    skills = Column(Text, nullable=True, default="[]") # Stored as JSON string or comma-separated values
    
    # Bank & Emergency Info
    emergency_contact = Column(String, nullable=True, default="N/A")
    relationship_with_emergency_contact = Column(String, nullable=True, default="N/A")
    bank_name = Column(String, nullable=True, default="N/A")
    bank_account = Column(String, nullable=True, default="N/A")
    ifsc_code = Column(String, nullable=True, default="N/A")
    qr_code = Column(String, nullable=True, default="N/A")
    upi_id = Column(String, nullable=True, default="N/A")
    
    # Additional
    resume = Column(String, nullable=True, default="N/A")
    photo = Column(String, nullable=True, default="N/A")
    additional_info = Column(String, nullable=True, default="N/A")
    reference_name = Column(String, nullable=True, default="N/A")
    biometric_attendance = Column(String, nullable=True, default="N/A")
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class LoginHistory(Base):
    """Audit trail for system logins across all roles."""
    __tablename__ = "login_history"
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=False) # Can link to Employees.id or Admins.id
    user_role = Column(String, nullable=False) # 'Admin', 'Employee', 'HR', etc.
    login_timestamp = Column(DateTime, default=datetime.now)
    ip_address = Column(String, nullable=True, default="Unknown")
    user_agent = Column(String, nullable=True, default="Unknown")

# ==========================================
#          PROJECTS & DOCUMENTATION
# ==========================================

class Projects(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=True, default="N/A")
    manager = Column(String, nullable=True, default="N/A manager")
    description = Column(String, nullable=True, default="N/A")
    status = Column(String, nullable=True, default="N/A")
    referred_by = Column(String, nullable=True, default="N/A")
    filled_by = Column(String, nullable=True, default="N/A")
    assigned_to = Column(String, nullable=True, default="N/A")
    cost_type = Column(String, nullable=True, default="N/A")
    client_cost = Column(Float, nullable=True, default=0.0)
    budget = Column(Float, nullable=True, default=0.0)
    start_date = Column(String, nullable=True, default="N/A")
    end_date = Column(String, nullable=True, default="N/A")
    team = Column(String, nullable=True, default="N/A")
    approx_cost = Column(Float, nullable=True, default=0.0)
    client = Column(String, nullable=True, default="N/A")
    progress = Column(String, nullable=True, default="N/A")
    
    # Link to active SRS document. 
    # Defined as string to avoid strict circular dependency with SRS_Documents table load order.
    srs_id = Column(String, ForeignKey("srs_documents.id"), nullable=True) 

    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

class ProjectAssignments(Base):
    __tablename__ = "project_assignments"
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    custom_hourly_cost = Column(Float, nullable=True)     # Overrides employee profile if set
    custom_hourly_billing = Column(Float, nullable=True)  # Overrides employee profile if set
    assigned_at = Column(DateTime, default=datetime.now)

class SRS_Documents(Base):
    """Software Requirements Specification document tracking."""
    __tablename__ = "srs_documents"
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    document_title = Column(String, nullable=False)
    version = Column(String, nullable=True, default="v1.0")
    file_url_or_path = Column(String, nullable=False)
    
    # NEW COLUMN for the parsed PDF content
    parsed_content = Column(Text, nullable=True) 
    
    approved_by = Column(String, nullable=True, default="N/A")
    status = Column(String, nullable=True, default="Draft")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class ProjectTimeline(Base):
    """Granular milestone tracking for projects."""
    __tablename__ = "project_timeline"
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    milestone_name = Column(String, nullable=False)
    expected_start = Column(DateTime, nullable=True)
    expected_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    status = Column(String, nullable=True, default="Pending") # Pending, Active, Delayed, Completed
    remarks = Column(Text, nullable=True, default="N/A")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

# ==========================================
#          TIMESHEETS & TASKS
# ==========================================

class DeveloperTasks(Base):
    """Timesheets explicitly for Engineering, IT, Design, and QA roles."""
    __tablename__ = "developer_tasks"
    id = Column(String, primary_key=True, default=generate_uuid)
    employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    
    date = Column(DateTime, default=datetime.now)
    hours_logged = Column(Float, nullable=False, default=0.0)
    
    # Dev Specifics
    tech_stack = Column(String, nullable=True, default="N/A")
    github_link = Column(String, nullable=True, default="N/A")
    task_performed = Column(Text, nullable=True, default="N/A")
    tomorrow_plan = Column(Text, nullable=True, default="N/A")
    
    # Auto-calculated Financials
    employee_cost = Column(Float, nullable=True, default=0.0)
    billing_amount = Column(Float, nullable=True, default=0.0)
    profit_loss = Column(Float, nullable=True, default=0.0)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class ContentCreatorTasks(Base):
    """Timesheets explicitly for Social Media, Video Editing, and Content roles."""
    __tablename__ = "content_creator_tasks"
    id = Column(String, primary_key=True, default=generate_uuid)
    employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    
    date = Column(DateTime, default=datetime.now)
    
    # Content Specifics
    reels_count = Column(Integer, nullable=True, default=0)
    long_video_count = Column(Integer, nullable=True, default=0)
    poster_count = Column(Integer, nullable=True, default=0)
    calls_made = Column(Integer, nullable=True, default=0)
    platform = Column(String, nullable=True, default="N/A") # e.g., Instagram, YouTube
    
    # Auto-calculated Total
    total_content = Column(Integer, nullable=True, default=0)
    
    # Auto-calculated Financials
    hours_logged = Column(Float, nullable=False, default=0.0)
    task_performed = Column(Text, nullable=True, default="N/A")
    employee_cost = Column(Float, nullable=True, default=0.0)
    billing_amount = Column(Float, nullable=True, default=0.0)
    profit_loss = Column(Float, nullable=True, default=0.0)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class Attendance(Base):
    __tablename__ = "attendance"
    id = Column(String, primary_key=True, default=generate_uuid)
    employee_id = Column(String, ForeignKey("employees.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    time_in = Column(DateTime, nullable=False)
    time_out = Column(DateTime, nullable=False)
    total_hours = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)