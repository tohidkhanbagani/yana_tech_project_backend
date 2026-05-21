from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy import func, desc, or_, and_, case, extract
from datetime import datetime, timedelta, time

from src.database.database_create import SessionLocal
from src.database.database_tables import (
    Projects, DeveloperTasks, ContentCreatorTasks,
    Employees, ProjectTimeline, SRS_Documents, Departments_Roles, Attendance,
    Clients, ProjectExpenses
)
from src.endpoints.auth import get_current_user

logger = logging.getLogger("Yana_Dashboard")
router = APIRouter(prefix="/dashboard", tags=["Executive Dashboard"])

# ==========================================
#          UTILITY: DATE RANGES
# ==========================================
def get_today_bounds():
    now = datetime.now()
    start_of_day = datetime.combine(now.date(), time.min)
    end_of_day = datetime.combine(now.date(), time.max)
    return start_of_day, end_of_day

def get_month_bounds():
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_of_month, now

def get_prev_month_bounds():
    now = datetime.now()
    start_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_of_prev_month = start_of_this_month - timedelta(seconds=1)
    start_of_prev_month = end_of_prev_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_of_prev_month, end_of_prev_month

# ==========================================
#        1. THE FINANCIAL SUITE
# ==========================================
@router.get("/financials", tags=["Executive Dashboard"])
def get_financial_suite(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Hawk-Eye view restricted to Administrators.")
    
    start_today, end_today = get_today_bounds()
    start_month, now = get_month_bounds()

    try:
        with SessionLocal() as session:
            # A. Cumulative Portfolio (All Time)
            cum_dev = session.query(
                func.coalesce(func.sum(DeveloperTasks.billing_amount), 0).label('total_billed'),
                func.coalesce(func.sum(DeveloperTasks.employee_cost), 0).label('total_cost')
            ).first()
            cum_content = session.query(
                func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0).label('total_billed'),
                func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0).label('total_cost')
            ).first()
            
            cum_billed = float(cum_dev.total_billed) + float(cum_content.total_billed)
            cum_cost = float(cum_dev.total_cost) + float(cum_content.total_cost)
            cum_profit = cum_billed - cum_cost
            cum_margin = (cum_profit / cum_billed * 100) if cum_billed > 0 else 0

            # B. Daily Burn vs Earn (Today)
            daily_dev = session.query(
                func.coalesce(func.sum(DeveloperTasks.billing_amount), 0).label('daily_billed'),
                func.coalesce(func.sum(DeveloperTasks.employee_cost), 0).label('daily_cost')
            ).filter(DeveloperTasks.date.between(start_today, end_today)).first()
            daily_content = session.query(
                func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0).label('daily_billed'),
                func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0).label('daily_cost')
            ).filter(ContentCreatorTasks.date.between(start_today, end_today)).first()
            
            daily_billed = float(daily_dev.daily_billed) + float(daily_content.daily_billed)
            daily_cost = float(daily_dev.daily_cost) + float(daily_content.daily_cost)

            # C. Monthly Burn vs Projected
            monthly_dev = session.query(
                func.coalesce(func.sum(DeveloperTasks.billing_amount), 0).label('monthly_billed'),
                func.coalesce(func.sum(DeveloperTasks.employee_cost), 0).label('monthly_cost')
            ).filter(DeveloperTasks.date.between(start_month, now)).first()
            monthly_content = session.query(
                func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0).label('monthly_billed'),
                func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0).label('monthly_cost')
            ).filter(ContentCreatorTasks.date.between(start_month, now)).first()
            
            monthly_billed = float(monthly_dev.monthly_billed) + float(monthly_content.monthly_billed)
            monthly_cost = float(monthly_dev.monthly_cost) + float(monthly_content.monthly_cost)

            # D. QUICK COMPUTE: Project Performance & Budget Health (Aggregated)
            # Use dictionary mapping to avoid N+1 queries in the loop
            dev_project_stats = {row.project_id: (float(row.profit or 0), float(row.cost or 0)) for row in session.query(
                DeveloperTasks.project_id,
                func.sum(DeveloperTasks.profit_loss).label('profit'),
                func.sum(DeveloperTasks.employee_cost).label('cost')
            ).group_by(DeveloperTasks.project_id).all()}

            content_project_stats = {row.project_id: (float(row.profit or 0), float(row.cost or 0)) for row in session.query(
                ContentCreatorTasks.project_id,
                func.sum(ContentCreatorTasks.profit_loss).label('profit'),
                func.sum(ContentCreatorTasks.employee_cost).label('cost')
            ).group_by(ContentCreatorTasks.project_id).all()}

            projects = session.query(Projects.id, Projects.name, Projects.budget).all()
            project_performance_list = []
            budget_warnings = []
            
            for p_id, p_name, p_budget in projects:
                d_prof, d_cost = dev_project_stats.get(p_id, (0.0, 0.0))
                c_prof, c_cost = content_project_stats.get(p_id, (0.0, 0.0))
                
                total_cost = d_cost + c_cost
                
                # Fetch actual project to get client_cost
                actual_proj = session.query(Projects).filter_by(id=p_id).first()
                actual_client_cost = float(actual_proj.client_cost) if actual_proj and actual_proj.client_cost else 0.0
                
                if actual_client_cost > 0:
                    total_profit = actual_client_cost - total_cost
                else:
                    total_profit = (d_prof + c_prof)
                
                project_performance_list.append({"project": p_name, "profit": total_profit})
                
                if p_budget and float(p_budget) > 0:
                    if total_cost >= (float(p_budget) * 0.8):
                        budget_warnings.append({"project": p_name, "budget": p_budget, "cost": total_cost})
            
            project_performance_list.sort(key=lambda x: x["profit"], reverse=True)

            return {
                "cumulative": {"billed": cum_billed, "cost": cum_cost, "profit": cum_profit, "margin_percent": round(cum_margin, 2)},
                "today": {"earned": daily_billed, "burned": daily_cost},
                "monthly": {"earned": monthly_billed, "burned": monthly_cost},
                "performers": {
                    "top": project_performance_list[:3],
                    "bottom": list(reversed(project_performance_list[-3:])) if len(project_performance_list) > 3 else []
                },
                "budget_warnings": budget_warnings
            }
    except Exception as e:
        logger.error(f"Dashboard Financials Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to aggregate financial suite.")

# ==========================================
#      2. PROJECT & DELIVERY HEALTH
# ==========================================
@router.get("/projects", tags=["Executive Dashboard"])
def get_project_health(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Administrators.")

    try:
        with SessionLocal() as session:
            # A. Global Project Counts
            active_count = session.query(Projects).filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%"))).count()
            pending_count = session.query(Projects).filter(Projects.status.ilike("%pending%")).count()
            completed_count = session.query(Projects).filter(Projects.status.ilike("%completed%")).count()

            # B. QUICK COMPUTE: Active Project Control Center
            active_projects = session.query(Projects).filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%"))).all()
            
            # Pre-fetch financials for all projects
            dev_financials = {row.project_id: (float(row.cost or 0), float(row.billed or 0)) for row in session.query(
                DeveloperTasks.project_id,
                func.sum(DeveloperTasks.employee_cost).label('cost'),
                func.sum(DeveloperTasks.billing_amount).label('billed')
            ).group_by(DeveloperTasks.project_id).all()}

            content_financials = {row.project_id: (float(row.cost or 0), float(row.billed or 0)) for row in session.query(
                ContentCreatorTasks.project_id,
                func.sum(ContentCreatorTasks.employee_cost).label('cost'),
                func.sum(ContentCreatorTasks.billing_amount).label('billed')
            ).group_by(ContentCreatorTasks.project_id).all()}

            # Pre-fetch active milestones
            active_milestones = {row.project_id: row for row in session.query(ProjectTimeline).filter(ProjectTimeline.status.ilike("%active%")).all()}

            control_center = []
            now = datetime.now()
            
            for proj in active_projects:
                d_cost, d_billed = dev_financials.get(proj.id, (0.0, 0.0))
                c_cost, c_billed = content_financials.get(proj.id, (0.0, 0.0))
                
                total_cost = d_cost + c_cost
                total_billed = d_billed + c_billed
                
                current_milestone = active_milestones.get(proj.id)
                
                health_tag = "🟢 On Track"
                if proj.budget and total_cost >= (float(proj.budget) * 0.9): health_tag = "🟡 Nearing Budget Limit"
                if current_milestone and current_milestone.expected_end and current_milestone.expected_end < now:
                    health_tag = "🔴 Timeline Delayed"

                if current_user.get("access_level") != "SystemAdmin":
                    total_cost = 0.0
                    total_billed = 0.0

                control_center.append({
                    "id": proj.id,
                    "name": proj.name,
                    "client": proj.client,
                    "budget": proj.budget,
                    "client_cost": float(proj.client_cost) if proj.client_cost else 0.0,
                    "accumulated_cost": total_cost,
                    "billed_to_date": total_billed,
                    "current_phase": current_milestone.milestone_name if current_milestone else "No Active Phase",
                    "health_indicator": health_tag
                })

            # C. SRS Compliance (Aggregated)
            non_compliant_srs = session.query(Projects.name).outerjoin(SRS_Documents, Projects.id == SRS_Documents.project_id)\
                                       .filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%")), SRS_Documents.id == None).all()

            return {
                "global_status": {"active": active_count, "pending": pending_count, "completed": completed_count},
                "active_control_center": control_center,
                "srs_compliance_warnings": [p.name for p in non_compliant_srs]
            }
    except Exception as e:
        logger.error(f"Dashboard Projects Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to aggregate project health.")

# ==========================================
#     3. ENGINEERING & CONTENT OUTPUT
# ==========================================
@router.get("/metrics", tags=["Executive Dashboard"])
def get_engineering_and_content_metrics(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Administrators.")
    
    start_today, end_today = get_today_bounds()

    try:
        with SessionLocal() as session:
            # A. Engineering Metrics
            dev_hours_today = session.query(func.coalesce(func.sum(DeveloperTasks.hours_logged), 0))\
                                     .filter(DeveloperTasks.date.between(start_today, end_today)).scalar()
            
            import json
            from collections import Counter
            all_tech_stacks = session.query(DeveloperTasks.tech_stack).filter(DeveloperTasks.tech_stack != "N/A").all()
            tech_counter = Counter()
            for row in all_tech_stacks:
                stack_val = row[0]
                if not stack_val or stack_val == "N/A" or stack_val == "[]":
                    continue
                try:
                    parsed = json.loads(stack_val)
                    if isinstance(parsed, list):
                        for t in parsed:
                            tech_counter[t.strip().lower()] += 1
                    else:
                        tech_counter[str(parsed).strip().lower()] += 1
                except:
                    for t in stack_val.split(','):
                        if t.strip():
                            tech_counter[t.strip().lower()] += 1

            tech_stack_dist = [(k, v) for k, v in tech_counter.items()]

            dev_leaderboard = session.query(
                Employees.full_name, func.coalesce(func.sum(DeveloperTasks.hours_logged), 0).label('hours')
            ).join(DeveloperTasks, Employees.id == DeveloperTasks.employee_id)\
             .group_by(Employees.id).order_by(desc('hours')).limit(5).all()

            # B. Content Metrics
            content_today = session.query(func.coalesce(func.sum(ContentCreatorTasks.total_content), 0))\
                                   .filter(ContentCreatorTasks.date.between(start_today, end_today)).scalar()
            
            creator_leaderboard = session.query(
                Employees.full_name, func.coalesce(func.sum(ContentCreatorTasks.total_content), 0).label('content')
            ).join(ContentCreatorTasks, Employees.id == ContentCreatorTasks.employee_id)\
             .group_by(Employees.id).order_by(desc('content')).limit(5).all()

            return {
                "engineering": {
                    "hours_today": float(dev_hours_today),
                    "tech_stack_distribution": {stack: count for stack, count in tech_stack_dist},
                    "leaderboard": [{"name": dev.full_name, "hours": float(dev.hours)} for dev in dev_leaderboard]
                },
                "content": {
                    "output_today": int(content_today),
                    "creator_leaderboard": [{"name": c.full_name, "total_pieces": int(c.content)} for c in creator_leaderboard]
                }
            }
    except Exception as e:
        logger.error(f"Dashboard Metrics Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to aggregate engineering and content metrics.")

# ==========================================
#          4. WORKFORCE RADAR
# ==========================================
@router.get("/workforce", tags=["Executive Dashboard"])
def get_workforce_overview(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Administrators.")
    
    start_today, end_today = get_today_bounds()

    try:
        with SessionLocal() as session:
            # Sync daily absences first
            from src.database.database_operations import DatabaseOperations
            db_ops = DatabaseOperations()
            db_ops.record_daily_absences_internal(session)

            total_employees = session.query(Employees).filter(Employees.is_active == True).count()
            
            # Count distinct employees who checked in today
            active_attendance = session.query(Attendance.employee_id).filter(
                Attendance.date.between(start_today, end_today),
                Attendance.status != "Absent"
            ).distinct().all()
            
            active_today = len(active_attendance)
            absent_today = total_employees - active_today

            # Resource Distribution (By Department)
            distribution = session.query(Departments_Roles.department_name, func.count(Employees.id))\
                                  .join(Employees, Departments_Roles.id == Employees.role_id)\
                                  .filter(Employees.is_active == True)\
                                  .group_by(Departments_Roles.department_name).all()

            # Query absent employees details
            absent_records = session.query(
                Employees.full_name,
                Employees.username,
                Departments_Roles.department_name
            ).join(
                Attendance, Attendance.employee_id == Employees.id
            ).outerjoin(
                Departments_Roles, Employees.role_id == Departments_Roles.id
            ).filter(
                Attendance.date.between(start_today, end_today),
                Attendance.status == "Absent",
                Employees.is_active == True
            ).all()

            absent_list = [
                {
                    "name": name or "Unknown",
                    "username": username or "N/A",
                    "department": dept or "General"
                }
                for name, username, dept in absent_records
            ]

            return {
                "radar": {
                    "total_staff": total_employees,
                    "active_today": active_today,
                    "absent_today": absent_today,
                    "absent_employees": absent_list
                },
                "resource_distribution": {dept: count for dept, count in distribution}
            }
    except Exception as e:
        logger.error(f"Dashboard Workforce Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to aggregate workforce radar.")

# ==========================================
#       5. THE MICE ON THE GROUND (FEED)
# ==========================================
@router.get("/live-feed", tags=["Executive Dashboard"])
def get_live_feed(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Administrators.")

    try:
        with SessionLocal() as session:
            feed = []
            
            # 1. Fetch Latest Developer Actions
            dev_tasks = session.query(DeveloperTasks, Employees.full_name, Projects.name)\
                               .join(Employees, DeveloperTasks.employee_id == Employees.id)\
                               .outerjoin(Projects, DeveloperTasks.project_id == Projects.id)\
                               .order_by(desc(DeveloperTasks.created_at)).limit(20).all()
            
            for t, emp_name, proj_name in dev_tasks:
                import json
                try:
                    parsed_tech = json.loads(t.tech_stack)
                    display_tech = ", ".join(parsed_tech) if isinstance(parsed_tech, list) else str(parsed_tech)
                except:
                    display_tech = t.tech_stack

                details_html = (
                    f"<strong>Hours:</strong> {t.hours_logged} hrs<br>"
                    f"<strong>Tech:</strong> {display_tech}<br>"
                    f"<strong>Task:</strong> {t.task_performed}<br>"
                    f"<strong>Plan for Tomorrow:</strong> {t.tomorrow_plan}"
                )

                
                feed.append({
                    "timestamp": t.created_at,
                    "type": "Engineering",
                    "employee": emp_name,
                    "project": proj_name or "General",
                    "details": details_html,
                    "link": t.github_link
                })

            # 2. Fetch Latest Content Actions
            content_tasks = session.query(ContentCreatorTasks, Employees.full_name, Projects.name)\
                                   .join(Employees, ContentCreatorTasks.employee_id == Employees.id)\
                                   .outerjoin(Projects, ContentCreatorTasks.project_id == Projects.id)\
                                   .order_by(desc(ContentCreatorTasks.created_at)).limit(20).all()

            for c, emp_name, proj_name in content_tasks:
                details_html = (
                    f"<strong>Hours:</strong> {c.hours_logged if hasattr(c, 'hours_logged') else 0} hrs<br>"
                    f"<strong>Task:</strong> {c.task_performed if hasattr(c, 'task_performed') else 'N/A'}<br>"
                    f"<strong>Output:</strong> {c.total_content} items ({c.reels_count} Reels, {c.long_video_count} Videos, {c.poster_count} Posters, {c.calls_made} Calls)<br>"
                    f"<strong>Platform:</strong> {c.platform}"
                )
                
                feed.append({
                    "timestamp": c.created_at,
                    "type": "Content",
                    "employee": emp_name,
                    "project": proj_name or "General",
                    "details": details_html,
                    "link": None
                })

            # Sort combined feed chronologically (newest first)
            feed.sort(key=lambda x: x["timestamp"], reverse=True)

            # 3. System Alerts (Projects with NO activity in 48 hours)
            two_days_ago = datetime.now() - timedelta(days=2)
            active_projs = session.query(Projects).filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%"))).all()
            alerts = []
            
            for proj in active_projs:
                recent_dev = session.query(DeveloperTasks.id).filter(DeveloperTasks.project_id == proj.id, DeveloperTasks.created_at >= two_days_ago).first()
                recent_content = session.query(ContentCreatorTasks.id).filter(ContentCreatorTasks.project_id == proj.id, ContentCreatorTasks.created_at >= two_days_ago).first()
                
                if not recent_dev and not recent_content:
                    alerts.append(f"⚠️ System Alert: No timesheets logged for project '{proj.name}' in the last 48 hours.")

            return {
                "live_stream": feed[:30], # Return the 30 most recent actions across the company
                "system_alerts": alerts
            }
    except Exception as e:
        logger.error(f"Dashboard Live Feed Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch live feed.")

# ==========================================
#       6. EMPLOYEE INDIVIDUAL ANALYTICS
# ==========================================
@router.get("/employee-analytics/{employee_id}", tags=["Executive Dashboard"])
def get_employee_analytics(employee_id: str, current_user: dict = Depends(get_current_user)):
    """Deep analytics for a single employee: Daily, Monthly, Yearly, Lifelong."""
    if current_user.get("role") != "admin" and current_user.get("id") != employee_id:
        raise HTTPException(status_code=403, detail="Unauthorized access to individual analytics.")

    start_today, end_today = get_today_bounds()
    start_month, now = get_month_bounds()
    start_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        with SessionLocal() as session:
            # 1. Daily (Today)
            daily_dev_hours = session.query(func.coalesce(func.sum(DeveloperTasks.hours_logged), 0))\
                                 .filter(DeveloperTasks.employee_id == employee_id, DeveloperTasks.date.between(start_today, end_today)).scalar()
            
            daily_content_hours = session.query(func.coalesce(func.sum(ContentCreatorTasks.hours_logged), 0))\
                                 .filter(ContentCreatorTasks.employee_id == employee_id, ContentCreatorTasks.date.between(start_today, end_today)).scalar()
            
            daily_content = session.query(func.coalesce(func.sum(ContentCreatorTasks.total_content), 0))\
                                   .filter(ContentCreatorTasks.employee_id == employee_id, ContentCreatorTasks.date.between(start_today, end_today)).scalar()
            
            # 2. Monthly
            monthly_dev = session.query(
                func.coalesce(func.sum(DeveloperTasks.hours_logged), 0).label('hours'),
                func.coalesce(func.sum(DeveloperTasks.billing_amount), 0).label('billed'),
                func.coalesce(func.sum(DeveloperTasks.employee_cost), 0).label('cost')
            ).filter(DeveloperTasks.employee_id == employee_id, DeveloperTasks.date.between(start_month, now)).first()

            monthly_content = session.query(
                func.coalesce(func.sum(ContentCreatorTasks.hours_logged), 0).label('hours'),
                func.coalesce(func.sum(ContentCreatorTasks.total_content), 0).label('count'),
                func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0).label('billed'),
                func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0).label('cost')
            ).filter(ContentCreatorTasks.employee_id == employee_id, ContentCreatorTasks.date.between(start_month, now)).first()

            # 3. Yearly
            yearly_dev_hours = session.query(func.coalesce(func.sum(DeveloperTasks.hours_logged), 0))\
                                .filter(DeveloperTasks.employee_id == employee_id, DeveloperTasks.date.between(start_year, now)).scalar()
            
            yearly_content_hours = session.query(func.coalesce(func.sum(ContentCreatorTasks.hours_logged), 0))\
                                .filter(ContentCreatorTasks.employee_id == employee_id, ContentCreatorTasks.date.between(start_year, now)).scalar()
            
            yearly_content = session.query(func.coalesce(func.sum(ContentCreatorTasks.total_content), 0))\
                                    .filter(ContentCreatorTasks.employee_id == employee_id, ContentCreatorTasks.date.between(start_year, now)).scalar()

            # 4. Lifelong & Projects
            all_time_dev = session.query(
                func.coalesce(func.sum(DeveloperTasks.hours_logged), 0).label('dev_hours'),
                func.coalesce(func.sum(DeveloperTasks.billing_amount), 0).label('total_billed'),
                func.coalesce(func.sum(DeveloperTasks.employee_cost), 0).label('total_cost')
            ).filter(DeveloperTasks.employee_id == employee_id).first()

            all_time_content = session.query(
                func.coalesce(func.sum(ContentCreatorTasks.hours_logged), 0).label('content_hours'),
                func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0).label('total_billed'),
                func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0).label('total_cost')
            ).filter(ContentCreatorTasks.employee_id == employee_id).first()

            # Project Distribution
            project_dist_dev = session.query(Projects.name, func.count(DeveloperTasks.id))\
                                  .join(DeveloperTasks, Projects.id == DeveloperTasks.project_id)\
                                  .filter(DeveloperTasks.employee_id == employee_id)\
                                  .group_by(Projects.name).all()
            
            project_dist_content = session.query(Projects.name, func.count(ContentCreatorTasks.id))\
                                  .join(ContentCreatorTasks, Projects.id == ContentCreatorTasks.project_id)\
                                  .filter(ContentCreatorTasks.employee_id == employee_id)\
                                  .group_by(Projects.name).all()

            dist_map = {}
            for name, count in project_dist_dev:
                dist_map[name] = dist_map.get(name, 0) + count
            for name, count in project_dist_content:
                dist_map[name] = dist_map.get(name, 0) + count

            return {
                "daily": {
                    "hours": float(daily_dev_hours + daily_content_hours),
                    "content_pieces": int(daily_content)
                },
                "monthly": {
                    "hours": float(monthly_dev.hours + monthly_content.hours),
                    "content": int(monthly_content.count),
                    "billed": float(monthly_dev.billed + monthly_content.billed),
                    "cost": float(monthly_dev.cost + monthly_content.cost)
                },
                "yearly": {
                    "hours": float(yearly_dev_hours + yearly_content_hours),
                    "content": int(yearly_content)
                },
                "lifelong": {
                    "total_hours": float(all_time_dev.dev_hours + all_time_content.content_hours),
                    "total_revenue": float(all_time_dev.total_billed + all_time_content.total_billed),
                    "total_cost": float(all_time_dev.total_cost + all_time_content.total_cost),
                    "project_distribution": dist_map
                }
            }
    except Exception as e:
        logger.error(f"Employee Analytics Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to calculate employee analytics.")

# ==========================================
#      7. THE ANALYTICS SUITE (SYSTEM OF CONTROL)
# ==========================================

@router.get("/analytics-suite", tags=["Executive Dashboard"])
def get_analytics_suite(current_user: dict = Depends(get_current_user)):
    """
    High-Signal Analytics Engine. 
    Implements the 12 critical metrics for organizational control.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Executive analytics restricted to Administrators.")

    try:
        with SessionLocal() as session:
            now = datetime.now()
            start_month, _ = get_month_bounds()
            
            # --- PRE-FETCH DATA FOR BULK AGGREGATION ---
            projects = session.query(Projects).all()
            employees = session.query(Employees).filter(Employees.is_active == True).all()
            
            # Financial Totals per Project
            dev_stats = {row.project_id: (float(row.cost or 0), float(row.billed or 0), float(row.hours or 0)) for row in session.query(
                DeveloperTasks.project_id,
                func.sum(DeveloperTasks.employee_cost).label('cost'),
                func.sum(DeveloperTasks.billing_amount).label('billed'),
                func.sum(DeveloperTasks.hours_logged).label('hours')
            ).group_by(DeveloperTasks.project_id).all()}

            content_stats = {row.project_id: (float(row.cost or 0), float(row.billed or 0), float(row.hours or 0)) for row in session.query(
                ContentCreatorTasks.project_id,
                func.sum(ContentCreatorTasks.employee_cost).label('cost'),
                func.sum(ContentCreatorTasks.billing_amount).label('billed'),
                func.sum(ContentCreatorTasks.hours_logged).label('hours')
            ).group_by(ContentCreatorTasks.project_id).all()}

            # Milestone Stats per Project
            milestone_counts = {row.project_id: (row.total, row.completed) for row in session.query(
                ProjectTimeline.project_id,
                func.count(ProjectTimeline.id).label('total'),
                func.sum(case((ProjectTimeline.status.ilike('%completed%'), 1), else_=0)).label('completed')
            ).group_by(ProjectTimeline.project_id).all()}

            # --- 1. COMPUTE METRICS --- 
            project_health = []
            profitability = []
            alerts = []
            
            for p in projects:
                d_cost, d_billed, d_hours = dev_stats.get(p.id, (0.0, 0.0, 0.0))
                c_cost, c_billed, c_hours = content_stats.get(p.id, (0.0, 0.0, 0.0))
                
                total_cost = d_cost + c_cost
                total_billed = d_billed + c_billed
                total_hours = d_hours + c_hours
                
                # A. Health Score (0-100)
                m_total, m_done = milestone_counts.get(p.id, (0, 0))
                completion_rate = (m_done / m_total) if m_total > 0 else 0
                
                budget_ratio = (total_cost / p.budget) if (p.budget and p.budget > 0) else 0
                budget_score = max(0, 1 - budget_ratio)
                
                # Simple Health Formula
                health_score = int((0.5 * completion_rate + 0.5 * budget_score) * 100)
                project_health.append({
                    "id": p.id,
                    "name": p.name,
                    "score": health_score,
                    "milestones_total": m_total,
                    "milestones_completed": m_done,
                    "completion_rate_percent": round(completion_rate * 100, 1),
                    "accumulated_cost": round(total_cost, 2),
                    "budget": float(p.budget or 0),
                    "budget_ratio_percent": round(budget_ratio * 100, 1),
                    "budget_score_percent": round(budget_score * 100, 1)
                })
                
                # B. Profitability
                actual_client_cost = float(p.client_cost) if p.client_cost else 0.0
                actual_revenue = actual_client_cost if actual_client_cost > 0 else total_billed
                
                profit = actual_revenue - total_cost
                margin = (profit / actual_revenue * 100) if actual_revenue > 0 else 0
                profitability.append({"project": p.name, "profit": profit, "margin": round(margin, 1)})
                
                # C. Risk Alerts
                if budget_ratio > 0.9 and completion_rate < 0.7:
                    alerts.append({"type": "critical", "message": f"Project '{p.name}' is over 90% budget but under 70% complete."})
                if margin < 0:
                    alerts.append({"type": "warning", "message": f"Project '{p.name}' is currently operating at a loss."})

            # D. Utilization & Idle Cost (Month-to-Date)
            working_days_mtd = (now - start_month).days + 1
            if working_days_mtd > 22: working_days_mtd = 22
            expected_hours = working_days_mtd * 8
            
            # Map role_id to department name for workforce categorisation
            role_mapping = {r.id: r.department_name for r in session.query(Departments_Roles).all()}
            
            utilization_list = []
            idle_leakage_details = []
            idle_cost_leakage = 0.0
            
            for emp in employees:
                emp_dev_hours = session.query(func.sum(DeveloperTasks.hours_logged)).filter(
                    DeveloperTasks.employee_id == emp.id, 
                    DeveloperTasks.date >= start_month
                ).scalar() or 0
                emp_content_hours = session.query(func.sum(ContentCreatorTasks.hours_logged)).filter(
                    ContentCreatorTasks.employee_id == emp.id, 
                    ContentCreatorTasks.date >= start_month
                ).scalar() or 0
                
                total_emp_hours = float(emp_dev_hours) + float(emp_content_hours)
                util = (total_emp_hours / expected_hours) if expected_hours > 0 else 0
                utilization_list.append({"name": emp.full_name, "utilization": round(util * 100, 1)})
                
                if util < 0.6:
                    leak = (expected_hours - total_emp_hours) * float(emp.hourly_cost_rate or 0)
                    idle_cost_leakage += leak
                    dept_name = role_mapping.get(emp.role_id, "General")
                    idle_leakage_details.append({
                        "employee_id": emp.id,
                        "employee_name": emp.full_name,
                        "department": dept_name,
                        "utilization": round(util * 100, 1),
                        "expected_hours": expected_hours,
                        "logged_hours": total_emp_hours,
                        "idle_hours": round(expected_hours - total_emp_hours, 1),
                        "hourly_rate": float(emp.hourly_cost_rate or 0),
                        "leakage_cost": round(leak, 2)
                    })

            return {
                "project_health": project_health,
                "profitability": profitability,
                "utilization": utilization_list,
                "idle_cost_leakage": round(idle_cost_leakage, 2),
                "idle_leakage_details": idle_leakage_details,
                "alerts": alerts,
                "meta": {
                    "last_updated": now.isoformat(),
                    "period": "Month-to-Date",
                    "working_days_mtd": working_days_mtd,
                    "expected_hours": expected_hours,
                    "calculation_formula": "Elapsed Days MTD (Max 22) × 8 expected hours/day"
                }
            }
    except Exception as e:
        logger.error(f"Analytics Suite Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute analytics suite.")

# ==========================================
#      8. V2 DASHBOARD SUMMARY (NEW)
# ==========================================
@router.get("/v2/summary", tags=["Executive Dashboard"])
def get_v2_dashboard_summary(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Administrators.")

    try:
        with SessionLocal() as session:
            now = datetime.now()
            
            # 1. Overview Stats
            total_projects = session.query(Projects).count()
            total_employees = session.query(Employees).filter(Employees.is_active == True).count()
            total_clients = session.query(Clients).count()
            
            dev_billed = session.query(func.coalesce(func.sum(DeveloperTasks.billing_amount), 0)).scalar()
            content_billed = session.query(func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0)).scalar()
            total_revenue = float(dev_billed) + float(content_billed)

            dev_cost = session.query(func.coalesce(func.sum(DeveloperTasks.employee_cost), 0)).scalar()
            content_cost = session.query(func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0)).scalar()
            expenses = session.query(func.coalesce(func.sum(ProjectExpenses.amount), 0)).scalar()
            total_expenditure = float(dev_cost) + float(content_cost) + float(expenses)

            # --- MoM KPI Trends Calculation ---
            start_month, now_month = get_month_bounds()
            start_prev_month, end_prev_month = get_prev_month_bounds()

            # Current Month Revenue (Billed Tasks)
            curr_dev_rev = session.query(func.coalesce(func.sum(DeveloperTasks.billing_amount), 0)).filter(DeveloperTasks.date.between(start_month, now_month)).scalar()
            curr_content_rev = session.query(func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0)).filter(ContentCreatorTasks.date.between(start_month, now_month)).scalar()
            curr_revenue = float(curr_dev_rev or 0) + float(curr_content_rev or 0)

            # Previous Month Revenue
            prev_dev_rev = session.query(func.coalesce(func.sum(DeveloperTasks.billing_amount), 0)).filter(DeveloperTasks.date.between(start_prev_month, end_prev_month)).scalar()
            prev_content_rev = session.query(func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0)).filter(ContentCreatorTasks.date.between(start_prev_month, end_prev_month)).scalar()
            prev_revenue = float(prev_dev_rev or 0) + float(prev_content_rev or 0)

            # Current Month Expenditure (Costs + Expenses)
            curr_dev_cost = session.query(func.coalesce(func.sum(DeveloperTasks.employee_cost), 0)).filter(DeveloperTasks.date.between(start_month, now_month)).scalar()
            curr_content_cost = session.query(func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0)).filter(ContentCreatorTasks.date.between(start_month, now_month)).scalar()
            curr_exp = session.query(func.coalesce(func.sum(ProjectExpenses.amount), 0)).filter(
                ProjectExpenses.expense_date.between(start_month.strftime("%Y-%m-%d"), now_month.strftime("%Y-%m-%d"))
            ).scalar()
            curr_burn = float(curr_dev_cost or 0) + float(curr_content_cost or 0) + float(curr_exp or 0)

            # Previous Month Expenditure
            prev_dev_cost = session.query(func.coalesce(func.sum(DeveloperTasks.employee_cost), 0)).filter(DeveloperTasks.date.between(start_prev_month, end_prev_month)).scalar()
            prev_content_cost = session.query(func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0)).filter(ContentCreatorTasks.date.between(start_prev_month, end_prev_month)).scalar()
            prev_exp = session.query(func.coalesce(func.sum(ProjectExpenses.amount), 0)).filter(
                ProjectExpenses.expense_date.between(start_prev_month.strftime("%Y-%m-%d"), end_prev_month.strftime("%Y-%m-%d"))
            ).scalar()
            prev_burn = float(prev_dev_cost or 0) + float(prev_content_cost or 0) + float(prev_exp or 0)

            # Trends Percentages
            revenue_trend = round(((curr_revenue - prev_revenue) / prev_revenue * 100), 2) if prev_revenue > 0 else (100.0 if curr_revenue > 0 else 0.0)
            burn_trend = round(((curr_burn - prev_burn) / prev_burn * 100), 2) if prev_burn > 0 else (100.0 if curr_burn > 0 else 0.0)

            # 2. Real Chart Data Aggregation (Optimized Bulk Queries)
            project_status = session.query(Projects.status, func.count(Projects.id)).group_by(Projects.status).all()
            project_status_counts = {status: count for status, count in project_status if status}

            milestone_status = session.query(ProjectTimeline.status, func.count(ProjectTimeline.id)).group_by(ProjectTimeline.status).all()
            milestone_counts = {status: count for status, count in milestone_status if status}

            departments = session.query(Departments_Roles.department_name, func.count(Employees.id))\
                                 .join(Employees, Departments_Roles.id == Employees.role_id)\
                                 .filter(Employees.is_active == True)\
                                 .group_by(Departments_Roles.department_name).all()
            dept_counts = {dept: count for dept, count in departments if dept}

            # Optimized Monthly Aggregation (Single Query for Dev and Content)
            current_year = now.year
            
            # Helper for monthly aggregation
            def get_monthly_stats(model, date_col, amount_col):
                return session.query(
                    extract('month', date_col).label('month'),
                    func.sum(amount_col).label('total')
                ).filter(extract('year', date_col) == current_year)\
                 .group_by('month').all()

            monthly_rev_dev = get_monthly_stats(DeveloperTasks, DeveloperTasks.date, DeveloperTasks.billing_amount)
            monthly_rev_content = get_monthly_stats(ContentCreatorTasks, ContentCreatorTasks.date, ContentCreatorTasks.billing_amount)
            
            monthly_cost_dev = get_monthly_stats(DeveloperTasks, DeveloperTasks.date, DeveloperTasks.employee_cost)
            monthly_cost_content = get_monthly_stats(ContentCreatorTasks, ContentCreatorTasks.date, ContentCreatorTasks.employee_cost)
            
            # Monthly Expenses
            monthly_exp_raw = session.query(
                func.substr(ProjectExpenses.expense_date, 6, 2).label('month'),
                func.sum(ProjectExpenses.amount).label('total')
            ).filter(ProjectExpenses.expense_date.like(f"{current_year}-%"))\
             .group_by('month').all()

            monthly_revenue = [0.0] * 12
            monthly_cost = [0.0] * 12
            
            for m, val in monthly_rev_dev: monthly_revenue[int(m)-1] += float(val or 0)
            for m, val in monthly_rev_content: monthly_revenue[int(m)-1] += float(val or 0)
            
            for m, val in monthly_cost_dev: monthly_cost[int(m)-1] += float(val or 0)
            for m, val in monthly_cost_content: monthly_cost[int(m)-1] += float(val or 0)
            for m, val in monthly_exp_raw: monthly_cost[int(m)-1] += float(val or 0)

            monthly_income = monthly_revenue
            monthly_pending = [0.0] * 12 # Future: Calculate pending invoices
            
            yearly_profit = {
                str(current_year): [round(rev - cost, 2) for rev, cost in zip(monthly_revenue, monthly_cost)]
            }

            # 3. Department P&L (Optimized)
            dept_pl_query_dev = session.query(
                Departments_Roles.department_name,
                func.sum(DeveloperTasks.billing_amount - DeveloperTasks.employee_cost).label('profit')
            ).join(Employees, DeveloperTasks.employee_id == Employees.id)\
             .join(Departments_Roles, Employees.role_id == Departments_Roles.id)\
             .group_by(Departments_Roles.department_name).all()

            dept_pl_query_content = session.query(
                Departments_Roles.department_name,
                func.sum(ContentCreatorTasks.billing_amount - ContentCreatorTasks.hours_logged * Employees.hourly_cost_rate if hasattr(ContentCreatorTasks, 'hours_logged') else ContentCreatorTasks.billing_amount - ContentCreatorTasks.employee_cost).label('profit')
            ).join(Employees, ContentCreatorTasks.employee_id == Employees.id)\
             .join(Departments_Roles, Employees.role_id == Departments_Roles.id)\
             .group_by(Departments_Roles.department_name).all()

            dept_pl = {}
            for d, p in dept_pl_query_dev: dept_pl[d] = dept_pl.get(d, 0) + float(p or 0)
            for d, p in dept_pl_query_content: dept_pl[d] = dept_pl.get(d, 0) + float(p or 0)

            # 4. Project Tracking (Optimized Bulk Query) 
            project_stats_dev = {row.project_id: (float(row.cost or 0), float(row.billed or 0)) for row in session.query(
                DeveloperTasks.project_id,
                func.sum(DeveloperTasks.employee_cost).label('cost'),
                func.sum(DeveloperTasks.billing_amount).label('billed')
            ).group_by(DeveloperTasks.project_id).all()}

            project_stats_content = {row.project_id: (float(row.cost or 0), float(row.billed or 0)) for row in session.query(
                ContentCreatorTasks.project_id,
                func.sum(ContentCreatorTasks.employee_cost).label('cost'),
                func.sum(ContentCreatorTasks.billing_amount).label('billed')
            ).group_by(ContentCreatorTasks.project_id).all()}

            project_expenses = {row.project_id: float(row.total or 0) for row in session.query(
                ProjectExpenses.project_id,
                func.sum(ProjectExpenses.amount).label('total')
            ).group_by(ProjectExpenses.project_id).all()}

            milestone_stats = {row.project_id: (row.total, row.completed) for row in session.query(
                ProjectTimeline.project_id, 
                func.count(ProjectTimeline.id).label('total'),
                func.sum(case((ProjectTimeline.status.ilike('%completed%'), 1), else_=0)).label('completed')
            ).group_by(ProjectTimeline.project_id).all()}

            projects_data = session.query(Projects).all()
            project_track = []
            for p in projects_data:
                d_c, d_b = project_stats_dev.get(p.id, (0.0, 0.0))
                c_c, c_b = project_stats_content.get(p.id, (0.0, 0.0))
                p_exp = project_expenses.get(p.id, 0.0)
                
                t_cost = d_c + c_c + p_exp
                t_billed = d_b + c_b
                
                actual_client_cost = float(p.client_cost) if p.client_cost else 0.0
                actual_revenue = actual_client_cost if actual_client_cost > 0 else t_billed
                
                margin = actual_revenue - t_cost
                margin_percent = (margin / actual_revenue * 100) if actual_revenue > 0 else 0
                
                b_val = float(p.budget) if p.budget and str(p.budget).replace(".","",1).isdigit() else 0.0
                spent_percent = (t_cost / b_val * 100) if b_val > 0 else 0

                # Dynamically compute project progress from milestones
                m_total, m_done = milestone_stats.get(p.id, (0, 0))
                if m_total > 0:
                    computed_progress = f"{int((m_done / m_total) * 100)}%"
                else:
                    computed_progress = p.progress or "0%"

                project_track.append({
                    "id": p.id,
                    "name": p.name or "Unnamed Project",
                    "status": p.status or "Pending",
                    "budget": b_val,
                    "client_cost": actual_revenue,
                    "percent_spent": round(spent_percent, 2),
                    "profit_margin": round(margin_percent, 2),
                    "progress": computed_progress,
                    "milestones": m_total
                })

            # 5. Employee Rankings (Optimized Bulk Query)
            employee_hours_dev = {row.employee_id: float(row.total or 0) for row in session.query(
                DeveloperTasks.employee_id, func.sum(DeveloperTasks.hours_logged).label('total')
            ).group_by(DeveloperTasks.employee_id).all()}

            employee_hours_content = {row.employee_id: float(row.total or 0) for row in session.query(
                ContentCreatorTasks.employee_id, func.sum(ContentCreatorTasks.hours_logged).label('total')
            ).group_by(ContentCreatorTasks.employee_id).all()}

            employees_data = session.query(Employees, Departments_Roles.role_name).outerjoin(Departments_Roles, Employees.role_id == Departments_Roles.id).filter(Employees.is_active == True).all()
            employee_rankings = []
            for emp, role in employees_data:
                total_h = employee_hours_dev.get(emp.id, 0.0) + employee_hours_content.get(emp.id, 0.0)
                efficiency = min(100.0, (total_h / 160) * 100) if total_h > 0 else 0.0
                employee_rankings.append({
                    "id": emp.id,
                    "name": emp.full_name or "Unnamed",
                    "role": role or "Staff",
                    "efficiency": round(efficiency, 2),
                    "tasks_completed": int(total_h / 2)
                })
            
            employee_rankings.sort(key=lambda x: x["efficiency"], reverse=True)

            # 6. Notifications
            notifications = []
            no_srs = session.query(Projects.name).outerjoin(SRS_Documents, Projects.id == SRS_Documents.project_id).filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%")), SRS_Documents.id == None).all()
            for p in no_srs:
                notifications.append({"type": "risk", "message": f"SRS missing for active project: {p.name}", "time": "Just now"})
            
            for p in project_track:
                if p["percent_spent"] > 90:
                    notifications.append({"type": "risk", "message": f"Project '{p['name']}' is nearing budget limit ({p['percent_spent']}% spent).", "time": "Today"})
                if p["profit_margin"] < 0:
                    notifications.append({"type": "risk", "message": f"Project '{p['name']}' is running at a loss.", "time": "Today"})

            avg_efficiency = round(sum(e["efficiency"] for e in employee_rankings) / len(employee_rankings), 2) if employee_rankings else 0.0
            
            # Recalculate total_revenue based on actual client costs (which is project_track's client_cost)
            real_total_revenue = sum(p["client_cost"] for p in project_track)

            return {
                "overview": {
                    "total_revenue": round(real_total_revenue, 2),
                    "total_projects": total_projects,
                    "total_employees": total_employees,
                    "total_clients": total_clients,
                    "total_expenditure": total_expenditure,
                    "avg_efficiency": avg_efficiency,
                    "revenue_trend": revenue_trend,
                    "burn_trend": burn_trend
                },
                "charts": {
                    "project_status": project_status_counts,
                    "milestone_status": milestone_counts,
                    "department_counts": dept_counts,
                    "monthly_revenue": [round(x, 2) for x in monthly_revenue],
                    "monthly_income": [round(x, 2) for x in monthly_income],
                    "monthly_pending": monthly_pending,
                    "dept_pl": {k: round(v, 2) for k, v in dept_pl.items()},
                    "yearly_profit": yearly_profit
                },
                "project_track": project_track,
                "employee_rankings": employee_rankings[:10], # Top 10 for dashboard
                "notifications": notifications
            }
    except Exception as e:
        logger.error(f"Dashboard v2 Summary Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load v2 summary.")

# ==========================================
#      9. DAILY WORK REPORT
# ==========================================
@router.get("/daily-report", tags=["Executive Dashboard"])
def get_daily_report(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Administrators.")

    start_today, end_today = get_today_bounds()

    try:
        with SessionLocal() as session:
            # Get present employees today (including "Check In" or any active status)
            active_attendance = session.query(Attendance.employee_id).filter(
                Attendance.date.between(start_today, end_today),
                Attendance.status != "Absent"
            ).distinct().all()
            
            # All active employees
            all_active_employees = session.query(Employees.id, Employees.full_name).filter(Employees.is_active == True).all()
            
            total_hours = 0.0
            total_present = 0
            attention_count = 0
            
            employees_data = []
            
            active_attendance_set = {a[0] for a in active_attendance}
            
            # Pre-fetch today's tasks
            dev_tasks_today = session.query(DeveloperTasks).filter(DeveloperTasks.date.between(start_today, end_today)).all()
            content_tasks_today = session.query(ContentCreatorTasks).filter(ContentCreatorTasks.date.between(start_today, end_today)).all()
            
            from collections import defaultdict
            emp_dev_tasks_map = defaultdict(list)
            for t in dev_tasks_today:
                emp_dev_tasks_map[t.employee_id].append(t)
                
            emp_content_tasks_map = defaultdict(list)
            for t in content_tasks_today:
                emp_content_tasks_map[t.employee_id].append(t)
            
            # Pre-fetch all projects to map id -> name
            projects = session.query(Projects.id, Projects.name).all()
            project_map = {p.id: p.name for p in projects}
            
            for emp_id, full_name in all_active_employees:
                # Is employee present?
                is_present = emp_id in active_attendance_set
                
                emp_dev_tasks = emp_dev_tasks_map.get(emp_id, [])
                emp_content_tasks = emp_content_tasks_map.get(emp_id, [])
                
                emp_hours = sum(float(t.hours_logged or 0) for t in emp_dev_tasks) + sum(float(t.hours_logged or 0) for t in emp_content_tasks)
                
                if not is_present and emp_hours == 0:
                    continue # Skip absent people who didn't work
                    
                total_present += 1
                total_hours += emp_hours
                
                utilization = (emp_hours / 8.0) * 100 if emp_hours > 0 else 0
                if utilization < 80 or emp_hours == 0:
                    attention_count += 1
                
                # Breakdown projects for employee
                emp_projects = {}
                for t in emp_dev_tasks:
                    p_name = project_map.get(t.project_id, "General/Unassigned")
                    emp_projects[p_name] = emp_projects.get(p_name, 0.0) + float(t.hours_logged or 0)
                for t in emp_content_tasks:
                    p_name = project_map.get(t.project_id, "General/Unassigned")
                    emp_projects[p_name] = emp_projects.get(p_name, 0.0) + float(t.hours_logged or 0)
                    
                employees_data.append({
                    "id": emp_id,
                    "name": full_name,
                    "hours": round(emp_hours, 2),
                    "utilization": round(utilization, 1),
                    "projects": [{"name": k, "hours": round(v, 2)} for k, v in emp_projects.items() if v > 0]
                })

            # Sort employees by hours descending
            employees_data.sort(key=lambda x: x["hours"], reverse=True)

            average_utilization = (total_hours / (total_present * 8.0) * 100) if total_present > 0 else 0
            
            # Project Overview Aggregation (Optimized Bulk SQL)
            now = datetime.now()
            start_today_dt = datetime.combine(now.date(), time.min)
            start_week_dt = datetime.combine((now - timedelta(days=now.weekday())).date(), time.min)
            start_month_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_year_dt = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            def get_project_time_stats(model):
                return session.query(
                    model.project_id,
                    func.sum(case((model.date >= start_today_dt, model.hours_logged), else_=0)).label('today'),
                    func.sum(case((model.date >= start_week_dt, model.hours_logged), else_=0)).label('week'),
                    func.sum(case((model.date >= start_month_dt, model.hours_logged), else_=0)).label('month'),
                    func.sum(case((model.date >= start_year_dt, model.hours_logged), else_=0)).label('year'),
                    func.sum(model.hours_logged).label('life')
                ).group_by(model.project_id).all()

            stats_dev = get_project_time_stats(DeveloperTasks)
            stats_content = get_project_time_stats(ContentCreatorTasks)
            
            project_stats_map = {}
            for row in stats_dev + stats_content:
                p_name = project_map.get(row.project_id, "General/Unassigned")
                if p_name not in project_stats_map:
                    project_stats_map[p_name] = {"today": 0.0, "week": 0.0, "month": 0.0, "year": 0.0, "life": 0.0}
                
                project_stats_map[p_name]["today"] += float(row.today or 0)
                project_stats_map[p_name]["week"] += float(row.week or 0)
                project_stats_map[p_name]["month"] += float(row.month or 0)
                project_stats_map[p_name]["year"] += float(row.year or 0)
                project_stats_map[p_name]["life"] += float(row.life or 0)
            
            total_today = sum(s["today"] for s in project_stats_map.values())
            
            project_overview = []
            for name, s in project_stats_map.items():
                if s["life"] > 0:
                    share = (s["today"] / total_today * 100) if total_today > 0 else 0
                    project_overview.append({
                        "name": name,
                        "share_percent": round(share, 1),
                        "today": round(s["today"], 2),
                        "week": round(s["week"], 2),
                        "month": round(s["month"], 2),
                        "year": round(s["year"], 2),
                        "life": round(s["life"], 2)
                    })
            
            project_overview.sort(key=lambda x: x["share_percent"], reverse=True)

            return {
                "kpis": {
                    "total_hours": round(total_hours, 2),
                    "employees_present": total_present,
                    "utilization_percent": round(average_utilization, 1),
                    "attention_count": attention_count
                },
                "employees": employees_data,
                "project_overview": project_overview
            }
    except Exception as e:
        logger.error(f"Dashboard Daily Report Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load daily report.")


@router.get("/manager/summary", tags=["Executive Dashboard"])
def get_manager_summary(current_user: dict = Depends(get_current_user)):
    """
    Dedicated analytics suite for Managers & System Admins.
    Calculates:
    - Projects completed before deadline.
    - Projects running at a financial loss.
    - Assigned resources presence/attendance stats.
    - Active projects managed by the user.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Restricted to Managers and Administrators.")

    from src.database.database_tables import Admins, Managers, ProjectAssignments, LeaveRequest

    manager_name = current_user.get("sub") # The manager's username/full_name
    
    try:
        with SessionLocal() as session:
            # A. Get all projects managed by this manager (or all projects if SystemAdmin)
            query = session.query(Projects)
            if current_user.get("access_level") == "ManagerAdmin":
                # Match either by username or full_name
                admin_user = session.query(Admins).filter_by(username=manager_name).first()
                mgr_names = [manager_name]
                if admin_user and admin_user.full_name and admin_user.full_name != "N/A":
                    mgr_names.append(admin_user.full_name)
                
                query = query.filter(or_(*[Projects.manager.ilike(f"%{name}%") for name in mgr_names]))
            
            projects = query.all()
            project_ids = [p.id for p in projects]
            
            # B. Projects stats
            total_projects = len(projects)
            active_projects = 0
            completed_projects = 0
            completed_before_deadline = 0
            running_at_loss = 0
            
            # Pre-fetch tasks and expenses for financial calculation
            dev_cost = {row.project_id: float(row.cost or 0) for row in session.query(
                DeveloperTasks.project_id, func.sum(DeveloperTasks.employee_cost).label('cost')
            ).filter(DeveloperTasks.project_id.in_(project_ids)).group_by(DeveloperTasks.project_id).all()} if project_ids else {}

            content_cost = {row.project_id: float(row.cost or 0) for row in session.query(
                ContentCreatorTasks.project_id, func.sum(ContentCreatorTasks.employee_cost).label('cost')
            ).filter(ContentCreatorTasks.project_id.in_(project_ids)).group_by(ContentCreatorTasks.project_id).all()} if project_ids else {}

            project_expenses = {row.project_id: float(row.amt or 0) for row in session.query(
                ProjectExpenses.project_id, func.sum(ProjectExpenses.amount).label('amt')
            ).filter(ProjectExpenses.project_id.in_(project_ids)).group_by(ProjectExpenses.project_id).all()} if project_ids else {}

            for proj in projects:
                status_lower = (proj.status or "").lower()
                if "active" in status_lower or "progress" in status_lower:
                    active_projects += 1
                elif "completed" in status_lower:
                    completed_projects += 1
                
                # Check completed before deadline
                if "completed" in status_lower:
                    milestones = session.query(ProjectTimeline).filter_by(project_id=proj.id).all()
                    proj_deadline = None
                    if proj.end_date and proj.end_date != "N/A":
                        try:
                            proj_deadline = datetime.strptime(proj.end_date, "%Y-%m-%d")
                        except ValueError:
                            try:
                                proj_deadline = datetime.fromisoformat(proj.end_date)
                            except ValueError:
                                pass
                    
                    if milestones:
                        if all(m.status == "Completed" for m in milestones):
                            actual_ends = [m.actual_end for m in milestones if m.actual_end]
                            if actual_ends:
                                latest_end = max(actual_ends)
                                if proj_deadline and latest_end <= proj_deadline:
                                    completed_before_deadline += 1
                            else:
                                if proj_deadline and proj.updated_at <= proj_deadline:
                                    completed_before_deadline += 1
                    else:
                        if proj_deadline and proj.updated_at <= proj_deadline:
                            completed_before_deadline += 1
                
                # Check running at a loss
                p_dev = dev_cost.get(proj.id, 0.0)
                p_content = content_cost.get(proj.id, 0.0)
                p_expenses = project_expenses.get(proj.id, 0.0)
                total_cost = p_dev + p_content + p_expenses
                
                revenue = float(proj.client_cost) if proj.client_cost else float(proj.budget or 0)
                if total_cost > revenue and revenue > 0:
                    running_at_loss += 1

            # C. Assigned resources & attendance
            # Get employee_ids assigned to manager's projects
            assignments = session.query(ProjectAssignments.employee_id).filter(ProjectAssignments.project_id.in_(project_ids)).distinct().all() if project_ids else []
            assigned_emp_ids = [a[0] for a in assignments]
            
            # Fetch assigned employee records
            assigned_employees = session.query(Employees).filter(Employees.id.in_(assigned_emp_ids)).all() if assigned_emp_ids else []
            total_resources = len(assigned_employees)
            
            # Check presence today
            start_today, end_today = get_today_bounds()
            present_today = 0
            if assigned_emp_ids:
                present_today = session.query(Attendance.employee_id).filter(
                    Attendance.employee_id.in_(assigned_emp_ids),
                    Attendance.date.between(start_today, end_today),
                    Attendance.status != "Absent"
                ).distinct().count()

            # Leave requests for assigned resources
            leave_requests = []
            if assigned_emp_ids:
                leaves = session.query(LeaveRequest, Employees.full_name).join(Employees, LeaveRequest.employee_id == Employees.id).filter(
                    LeaveRequest.employee_id.in_(assigned_emp_ids)
                ).order_by(desc(LeaveRequest.created_at)).limit(10).all()
                for l, full_name in leaves:
                    leave_requests.append({
                        "id": l.id,
                        "employee_id": l.employee_id,
                        "employee_name": full_name,
                        "start_date": l.start_date.isoformat() if l.start_date else None,
                        "end_date": l.end_date.isoformat() if l.end_date else None,
                        "reason": l.reason,
                        "status": l.status,
                        "created_at": l.created_at.isoformat() if l.created_at else None
                    })

            # General attendance logs for these resources
            attendance_history = []
            if assigned_emp_ids:
                attn = session.query(Attendance, Employees.full_name).join(Employees, Attendance.employee_id == Employees.id).filter(
                    Attendance.employee_id.in_(assigned_emp_ids)
                ).order_by(desc(Attendance.date)).limit(10).all()
                for a, full_name in attn:
                    attendance_history.append({
                        "employee_name": full_name,
                        "date": a.date.isoformat() if a.date else None,
                        "status": a.status,
                        "check_in": a.check_in_time.isoformat() if a.check_in_time else None,
                        "check_out": a.check_out_time.isoformat() if a.check_out_time else None
                    })

            return {
                "projects": {
                    "total": total_projects,
                    "active": active_projects,
                    "completed": completed_projects,
                    "completed_before_deadline": completed_before_deadline,
                    "running_at_loss": running_at_loss
                },
                "resources": {
                    "total": total_resources,
                    "present_today": present_today,
                    "attendance_rate": round((present_today / total_resources * 100), 1) if total_resources > 0 else 100.0
                },
                "leave_requests": leave_requests,
                "attendance_history": attendance_history
            }
    except Exception as e:
        logger.error(f"Manager Summary Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load manager summary data.")
