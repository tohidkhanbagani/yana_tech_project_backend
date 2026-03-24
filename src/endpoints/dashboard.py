from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy import func, desc, or_, and_
from datetime import datetime, timedelta, time

from src.database.database_create import SessionLocal
from src.database.database_tables import (
    Projects, DeveloperTasks, ContentCreatorTasks, 
    Employees, ProjectTimeline, SRS_Documents, Departments_Roles
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

            # D. Top & Bottom Performers (Combined)
            projects = session.query(Projects).all()
            project_performance_list = []
            budget_warnings = []
            
            for p in projects:
                d_profit = session.query(func.coalesce(func.sum(DeveloperTasks.profit_loss), 0)).filter(DeveloperTasks.project_id == p.id).scalar()
                c_profit = session.query(func.coalesce(func.sum(ContentCreatorTasks.profit_loss), 0)).filter(ContentCreatorTasks.project_id == p.id).scalar()
                total_profit = float(d_profit) + float(c_profit)
                project_performance_list.append({"project": p.name, "profit": total_profit})
                
                # E. Budget Health Warnings (Cost > 80% of Budget)
                if p.budget and float(p.budget) > 0:
                    d_cost = session.query(func.coalesce(func.sum(DeveloperTasks.employee_cost), 0)).filter(DeveloperTasks.project_id == p.id).scalar()
                    c_cost = session.query(func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0)).filter(ContentCreatorTasks.project_id == p.id).scalar()
                    total_p_cost = float(d_cost) + float(c_cost)
                    if total_p_cost >= (p.budget * 0.8):
                        budget_warnings.append({"project": p.name, "budget": p.budget, "cost": total_p_cost})
            
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
            active = session.query(Projects).filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%"))).count()
            pending = session.query(Projects).filter(Projects.status.ilike("%pending%")).count()
            completed = session.query(Projects).filter(Projects.status.ilike("%completed%")).count()

            # B. Active Project Control Center & Milestone Radar
            active_projects = session.query(Projects).filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%"))).all()
            control_center = []
            
            for proj in active_projects:
                # Get financials
                costs_dev = session.query(
                    func.coalesce(func.sum(DeveloperTasks.employee_cost), 0).label('cost'),
                    func.coalesce(func.sum(DeveloperTasks.billing_amount), 0).label('billed')
                ).filter(DeveloperTasks.project_id == proj.id).first()
                costs_content = session.query(
                    func.coalesce(func.sum(ContentCreatorTasks.employee_cost), 0).label('cost'),
                    func.coalesce(func.sum(ContentCreatorTasks.billing_amount), 0).label('billed')
                ).filter(ContentCreatorTasks.project_id == proj.id).first()
                
                total_cost = float(costs_dev.cost) + float(costs_content.cost)
                total_billed = float(costs_dev.billed) + float(costs_content.billed)
                
                # Get timeline & milestone risk
                current_milestone = session.query(ProjectTimeline).filter(
                    ProjectTimeline.project_id == proj.id, 
                    ProjectTimeline.status.ilike("%active%")
                ).first()
                
                health_tag = "🟢 On Track"
                if total_cost >= (proj.budget * 0.9): health_tag = "🟡 Nearing Budget Limit"
                if current_milestone and current_milestone.expected_end and current_milestone.expected_end < datetime.now():
                    health_tag = "🔴 Timeline Delayed"

                control_center.append({
                    "id": proj.id,
                    "name": proj.name,
                    "client": proj.client,
                    "budget": proj.budget,
                    "accumulated_cost": total_cost,
                    "billed_to_date": total_billed,
                    "current_phase": current_milestone.milestone_name if current_milestone else "No Active Phase",
                    "health_indicator": health_tag
                })

            # C. SRS Compliance (Active projects missing SRS)
            non_compliant_srs = session.query(Projects.name).outerjoin(SRS_Documents, Projects.id == SRS_Documents.project_id)\
                                       .filter(or_(Projects.status.ilike("%active%"), Projects.status.ilike("%in progress%")), SRS_Documents.id == None).all()

            return {
                "global_status": {"active": active, "pending": pending, "completed": completed},
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
            total_employees = session.query(Employees).filter(Employees.is_active == True).count()
            
            # Count distinct employees who logged ANY task today
            active_devs = session.query(DeveloperTasks.employee_id).filter(DeveloperTasks.date.between(start_today, end_today)).distinct().all()
            active_creators = session.query(ContentCreatorTasks.employee_id).filter(ContentCreatorTasks.date.between(start_today, end_today)).distinct().all()
            
            active_ids = set([d[0] for d in active_devs] + [c[0] for c in active_creators])
            active_today = len(active_ids)
            absent_today = total_employees - active_today

            # Resource Distribution (By Department)
            distribution = session.query(Departments_Roles.department_name, func.count(Employees.id))\
                                  .join(Employees, Departments_Roles.id == Employees.role_id)\
                                  .filter(Employees.is_active == True)\
                                  .group_by(Departments_Roles.department_name).all()

            return {
                "radar": {"total_staff": total_employees, "active_today": active_today, "absent_today": absent_today},
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