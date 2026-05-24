from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict
from typing import Optional, List, Union
from datetime import datetime

# ==========================================
#              BASE CONFIGURATION
# ==========================================
class ConfiguredBaseModel(BaseModel):
    """
    Base model allowing SQLAlchemy object parsing and mapping.
    Prevents extra fields from sneaking into the database payloads.
    """
    model_config = ConfigDict(from_attributes=True, extra="forbid")

# ==========================================
#        DEPARTMENTS & ROLES SCHEMAS
# ==========================================
class DepartmentRoleCreate(ConfiguredBaseModel):
    department_name: str = Field(..., min_length=2, description="Name of the department (e.g., IT, HR)")
    role_name: str = Field(..., min_length=2, description="Specific role (e.g., Java Developer, Video Editor)")
    is_active: Optional[bool] = True

class DepartmentRoleUpdate(ConfiguredBaseModel):
    department_name: Optional[str] = Field(None, min_length=2)
    role_name: Optional[str] = Field(None, min_length=2)
    is_active: Optional[bool] = None

# ==========================================
#              ADMIN SCHEMAS
# ==========================================
class AdminCreate(ConfiguredBaseModel):
    username: str = Field(..., min_length=4, max_length=50, description="Unique login ID")
    password: Optional[str] = Field(None, min_length=8, description="Must be at least 8 characters")
    email: Optional[EmailStr] = Field(None, description="Valid email address")
    full_name: Optional[str] = Field("N/A", description="Admin's full name")
    access_level: Optional[str] = Field("SystemAdmin", description="Privilege level (e.g., SuperAdmin, SystemAdmin)")

class AdminUpdate(ConfiguredBaseModel):
    password: Optional[str] = Field(None, min_length=8)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    access_level: Optional[str] = None

# ==========================================
#             EMPLOYEE SCHEMAS
# ==========================================
class EmployeeCreate(ConfiguredBaseModel):
    # Credentials
    username: Optional[str] = Field(None, description="Auto-generated if left blank")
    password: Optional[str] = Field(None, description="Auto-generated if left blank")
    role_id: Optional[str] = Field(None, description="UUID from Departments_Roles table")
    
    # HR Data
    full_name: str = Field(..., min_length=2, description="Employee's full legal name")
    email: Optional[EmailStr] = None
    contact_number: Optional[str] = Field(None, description="Primary contact number")
    
    # Financial Auto-Calc Factors
    hourly_cost_rate: Optional[float] = Field(0.0, ge=0.0, description="Cost to the company per hour")
    hourly_billing_rate: Optional[float] = Field(0.0, ge=0.0, description="Amount billed to client per hour")
    salary: Optional[float] = Field(0.0, ge=0.0, description="Monthly salary")
    
    # Keeping it flexible for the myriad of string fields in your DB
    department: Optional[str] = "N/A"
    skills: Optional[str] = Field("[]", description="JSON string array or comma-separated string of skills")
    
    # Fallback to catch any remaining DB fields you want to pass on creation
    model_config = ConfigDict(extra="allow", from_attributes=True) 

class EmployeeUpdate(ConfiguredBaseModel):
    password: Optional[str] = Field(None, min_length=8)
    role_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    hourly_cost_rate: Optional[float] = Field(None, ge=0.0)
    hourly_billing_rate: Optional[float] = Field(None, ge=0.0)
    skills: Optional[str] = None
    is_active: Optional[bool] = None
    
    model_config = ConfigDict(extra="allow", from_attributes=True) 

class ManagerCreate(ConfiguredBaseModel):
    name: str = Field(..., min_length=2, description="Manager Name")

class ClientCreate(ConfiguredBaseModel):
    name: str = Field(..., min_length=2, description="Client Name")
    company: Optional[str] = Field("N/A", description="Company Name")
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field("N/A", description="Contact Number")
    address: Optional[str] = Field("N/A", description="Physical Address")

class ClientUpdate(ConfiguredBaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None

# ==========================================
#        PROJECT & TIMELINE SCHEMAS
# ==========================================
class ProjectCreate(ConfiguredBaseModel):
    name: str = Field(..., min_length=2, description="Project Name")
    project_type: Optional[str] = Field("Engineering", description="Engineering, Content, or Both")
    project_platform: Optional[str] = Field("Generic project", description="Platform of the project (e.g., Web, Mobile, etc.)")
    description: Optional[str] = Field("N/A", description="Project description or notes")
    status: Optional[str] = Field("Pending", description="Pending, Active, Completed, Cancelled")
    client_cost: Optional[float] = Field(0.0, ge=0.0)
    budget: Optional[float] = Field(0.0, ge=0.0)
    approx_cost: Optional[float] = Field(0.0, ge=0.0)
    cost_type: Optional[str] = Field("N/A", description="Billing/Cost Type (e.g. Fixed Price, Hourly)")
    start_date: Optional[str] = "N/A"
    end_date: Optional[str] = "N/A"
    progress: Optional[str] = "0%"
    manager: Optional[str] = "N/A"
    client: Optional[str] = "N/A"
    referred_by: Optional[str] = "N/A"
    filled_by: Optional[str] = "N/A"
    assigned_to: Optional[str] = "N/A"
    team: Optional[str] = "N/A"
    srs_id: Optional[str] = Field(None, description="UUID of the linked SRS Document")

    model_config = ConfigDict(extra="allow")

class ProjectUpdate(ConfiguredBaseModel):
    name: Optional[str] = None
    project_type: Optional[str] = None
    project_platform: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    client_cost: Optional[float] = None
    budget: Optional[float] = None
    approx_cost: Optional[float] = None
    cost_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    progress: Optional[str] = None
    manager: Optional[str] = None
    client: Optional[str] = None
    referred_by: Optional[str] = None
    filled_by: Optional[str] = None
    assigned_to: Optional[str] = None
    team: Optional[str] = None
    srs_id: Optional[str] = None
    model_config = ConfigDict(extra="allow")

class ProjectExpenseCreate(ConfiguredBaseModel):
    project_id: str
    expense_name: str
    amount: float = Field(..., gt=0.0)
    expense_date: Optional[str] = "N/A"
    description: Optional[str] = "N/A"

class ProjectPaymentCreate(ConfiguredBaseModel):
    project_id: str = Field(..., description="UUID of the Project")
    amount: float = Field(..., gt=0.0, description="Amount paid by the client")
    payment_date: Optional[datetime] = Field(default_factory=datetime.now)
    payment_method: Optional[str] = "Bank Transfer"
    reference_number: Optional[str] = "N/A"
    remarks: Optional[str] = "N/A"

class ProjectPaymentUpdate(ConfiguredBaseModel):
    amount: Optional[float] = Field(None, gt=0.0)
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    remarks: Optional[str] = None

class ProjectAssignmentCreate(ConfiguredBaseModel):
    project_id: str = Field(..., description="UUID of the Project")
    employee_id: str = Field(..., description="UUID of the Employee")
    custom_hourly_billing: Optional[float] = Field(None, ge=0.0)

class MilestoneAssignmentCreate(ConfiguredBaseModel):
    milestone_id: str = Field(..., description="UUID of the Milestone")
    employee_id: str = Field(..., description="UUID of the Employee")

class SRSCreate(ConfiguredBaseModel):
    project_id: str = Field(..., description="UUID of the parent project")
    document_title: str = Field(..., description="Title of the SRS document")
    version: Optional[str] = "v1.0"
    file_url_or_path: str = Field(..., description="Location of the stored file")
    status: Optional[str] = Field("Draft", description="Draft, Approved, Archived")

class TimelineCreate(ConfiguredBaseModel):
    project_id: str = Field(..., description="UUID of the parent project")
    milestone_name: str = Field(..., description="E.g., Phase 1: UI Design")
    expected_start: Optional[datetime] = None
    expected_end: Optional[datetime] = None
    status: Optional[str] = "Pending"
    remarks: Optional[str] = "N/A"

    @field_validator('expected_end')
    def validate_dates(cls, expected_end, info):
        """High-end validation: Ensure end date is not before start date"""
        expected_start = info.data.get('expected_start')
        if expected_start and expected_end and expected_end < expected_start:
            raise ValueError("expected_end cannot be earlier than expected_start")
        return expected_end

# ==========================================
#          TIMESHEET / TASK SCHEMAS
# ==========================================
class DeveloperTaskCreate(ConfiguredBaseModel):
    """
    Validation for Engineers, QA, and Designers.
    Notice that employee_cost, billing_amount, and profit_loss are INTENTIONALLY EXCLUDED 
    from this schema so the frontend cannot fake financial data.
    """
    employee_id: str = Field(..., description="UUID of the employee logging the task")
    project_id: Optional[str] = Field(None, description="UUID of the project")
    milestone_id: Optional[str] = Field(None, description="UUID of the milestone")
    date: Optional[datetime] = Field(default_factory=datetime.now)

    hours_logged: float = Field(..., gt=0.0, le=24.0, description="Must be greater than 0 and max 24")
    tech_stack: Optional[str] = "N/A"    
    github_link: Optional[str] = "N/A"
    task_performed: str = Field(..., min_length=5, description="Description of the work done")
    tomorrow_plan: Optional[str] = "N/A"

class DeveloperTaskUpdate(ConfiguredBaseModel):
    hours_logged: Optional[float] = Field(None, gt=0.0, le=24.0)
    tech_stack: Optional[str] = None
    github_link: Optional[str] = None
    task_performed: Optional[str] = None
    tomorrow_plan: Optional[str] = None

class ContentTaskCreate(ConfiguredBaseModel):
    """
    Validation for Social Media and Content teams.
    Notice that total_content is INTENTIONALLY EXCLUDED so the frontend cannot fake metrics.
    """
    employee_id: str = Field(..., description="UUID of the employee logging the task")
    project_id: Optional[str] = Field(None, description="UUID of the project")
    milestone_id: Optional[str] = Field(None, description="UUID of the milestone")
    date: Optional[datetime] = Field(default_factory=datetime.now)

    hours_logged: float = Field(..., gt=0.0, le=24.0, description="Must be greater than 0 and max 24")
    task_performed: str = Field(..., min_length=5, description="Description of the work done")    
    reels_count: Optional[int] = Field(0, ge=0, description="Cannot be negative")
    long_video_count: Optional[int] = Field(0, ge=0, description="Cannot be negative")
    poster_count: Optional[int] = Field(0, ge=0, description="Cannot be negative")
    calls_made: Optional[int] = Field(0, ge=0, description="Cannot be negative")
    platform: Optional[str] = "N/A"

class ContentTaskUpdate(ConfiguredBaseModel):
    reels_count: Optional[int] = Field(None, ge=0)
    long_video_count: Optional[int] = Field(None, ge=0)
    poster_count: Optional[int] = Field(None, ge=0)
    calls_made: Optional[int] = Field(None, ge=0)
    platform: Optional[str] = None

# ==========================================
#          EXTENDED UPDATE SCHEMAS
# ==========================================
class SRSUpdate(ConfiguredBaseModel):
    document_title: Optional[str] = None
    version: Optional[str] = None
    file_url_or_path: Optional[str] = None
    status: Optional[str] = None
    approved_by: Optional[str] = None

class TimelineUpdate(ConfiguredBaseModel):
    milestone_name: Optional[str] = None
    expected_start: Optional[datetime] = None
    expected_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    status: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator('expected_end')
    def validate_expected_dates(cls, expected_end, info):
        expected_start = info.data.get('expected_start')
        if expected_start and expected_end and expected_end < expected_start:
            raise ValueError("expected_end cannot be earlier than expected_start")
        return expected_end

    @field_validator('actual_end')
    def validate_actual_dates(cls, actual_end, info):
        actual_start = info.data.get('actual_start')
        if actual_start and actual_end and actual_end < actual_start:
            raise ValueError("actual_end cannot be earlier than actual_start")
        return actual_end