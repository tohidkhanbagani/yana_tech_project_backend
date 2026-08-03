"""
Yana OS - Core Billing Calculation Engine
Module: src/billing/billing_engine.py

Provides unified, dynamic billing cycle generation, cost type normalization,
recurrence interval calculation, and task financial metrics computation.
Includes strict guard rails, boundary validations, and zero-leakage error handling.
"""

import logging
from datetime import datetime, timedelta
import calendar
from typing import List, Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Canonical Billing Cost Types
VALID_COST_TYPES = [
    "Fixed Price",
    "Time & Material",
    "Internal / Non-Billable"
]

class BillingEngine:
    @staticmethod
    def normalize_cost_type(cost_type: Optional[str]) -> str:
        """
        Validates and normalizes input cost_type string against valid platform types.
        Legacy 'Time and Material', 'Hourly Billing', or 'Monthly Retainer' are normalized to 'Time & Material'.
        Unrecognized types fall back to 'Internal / Non-Billable'.
        """
        if not cost_type:
            return "Internal / Non-Billable"
        
        cleaned = cost_type.strip()
        if cleaned in ["Time and Material", "Time & Material", "Monthly Retainer", "Hourly Billing"]:
            return "Time & Material"
        elif cleaned == "Fixed Price":
            return "Fixed Price"
        elif cleaned in ["Internal / Non-Billable", "Internal"]:
            return "Internal / Non-Billable"
        
        logger.warning(f"Unrecognized cost_type '{cost_type}' received. Defaulting to 'Internal / Non-Billable'.")
        return "Internal / Non-Billable"

    @staticmethod
    def add_months(sourcedate: datetime, months: int) -> datetime:
        """
        Helper method to add N calendar months to a datetime object safely,
        clamping the day to valid max days in target month.
        """
        month = sourcedate.month - 1 + months
        year = sourcedate.year + month // 12
        month = month % 12 + 1
        day = min(sourcedate.day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)

    @classmethod
    def calculate_cycle_dates(
        cls,
        start_date: datetime,
        end_boundary: datetime,
        cycle_type: str,
        interval_days: Optional[int] = None,
        max_cycles: int = 100
    ) -> List[datetime]:
        """
        Calculates all billing cycle dates between start_date and end_boundary.
        Handles Hourly (1 day / logged hours), Weekly (7 days), 15 Days (15 days),
        Monthly Retainer (1 month), Yearly (12 months), and Custom Date/Days (interval_days).
        """
        cycle_str = str(cycle_type or "").lower().strip()
        cycle_dates = []
        i = 0

        # Guard rails for invalid or future boundaries
        if start_date > end_boundary:
            cycle_dates.append(start_date)
            return cycle_dates

        while i < max_cycles:
            if "yearly" in cycle_str or interval_days == 365:
                b_date = cls.add_months(start_date, i * 12)
            elif "weekly" in cycle_str or interval_days == 7:
                b_date = start_date + timedelta(days=i * 7)
            elif "15" in cycle_str or interval_days == 15:
                b_date = start_date + timedelta(days=i * 15)
            elif "hourly" in cycle_str or interval_days == 1:
                b_date = start_date + timedelta(days=i * 1)
            elif interval_days and interval_days > 0 and interval_days != 30:
                b_date = start_date + timedelta(days=i * interval_days)
            else:
                # Default: Monthly Retainer / Monthly
                b_date = cls.add_months(start_date, i)

            if b_date > end_boundary and i > 0:
                break

            cycle_dates.append(b_date)
            i += 1

        return cycle_dates

    @classmethod
    def sync_project_billing_cycles(cls, session, proj, project_billing_model) -> None:
        """
        Synchronizes project billing records in the DB based on the project's cost_type,
        billing_cycle, and billing_interval_days.
        Void/deletes obsolete billing records of other cost types.
        Calculates dynamic cycle records cleanly.
        """
        try:
            raw_cost_type = proj.cost_type or "Internal / Non-Billable"
            normalized_type = cls.normalize_cost_type(raw_cost_type)

            # 1. Delete billing records belonging to OTHER billing types
            other_billings = session.query(project_billing_model).filter(
                project_billing_model.project_id == proj.id,
                project_billing_model.billing_type != normalized_type
            ).all()
            for ob in other_billings:
                session.delete(ob)
            session.flush()

            # 2. Process Fixed Price vs Time & Material vs Non-Billable
            if normalized_type == "Fixed Price":
                contract_billing = session.query(project_billing_model).filter_by(
                    project_id=proj.id,
                    billing_type="Fixed Price"
                ).first()
                amount = float(proj.client_cost or 0.0)
                if contract_billing:
                    contract_billing.amount = amount
                    contract_billing.description = "Fixed Price - Contract Value"
                else:
                    new_b = project_billing_model(
                        project_id=proj.id,
                        amount=amount,
                        billing_type="Fixed Price",
                        description="Fixed Price - Contract Value",
                        status="Billed",
                        billing_date=proj.created_at or datetime.now()
                    )
                    session.add(new_b)

            elif normalized_type == "Time & Material":
                start_date = None
                if proj.start_date and proj.start_date != "N/A":
                    try:
                        start_date = datetime.strptime(proj.start_date.strip(), "%Y-%m-%d")
                    except ValueError:
                        pass
                if not start_date:
                    start_date = proj.created_at or datetime.now()

                end_boundary = datetime.now()
                if proj.status in ["Completed", "Cancelled"] and proj.end_date and proj.end_date != "N/A":
                    try:
                        end_boundary = datetime.strptime(proj.end_date.strip(), "%Y-%m-%d")
                    except ValueError:
                        pass

                cycle_dates = cls.calculate_cycle_dates(
                    start_date=start_date,
                    end_boundary=end_boundary,
                    cycle_type=proj.billing_cycle or "Monthly",
                    interval_days=proj.billing_interval_days
                )

                billing_rate = float(proj.billing_rate or 0.0)
                for idx, b_date in enumerate(cycle_dates):
                    description = f"Time & Material - Cycle {idx+1} ({b_date.strftime('%Y-%m-%d')})"
                    existing = session.query(project_billing_model).filter(
                        project_billing_model.project_id == proj.id,
                        project_billing_model.billing_type == "Time & Material",
                        project_billing_model.description == description
                    ).first()

                    if existing:
                        existing.amount = billing_rate
                    else:
                        new_mb = project_billing_model(
                            project_id=proj.id,
                            amount=billing_rate,
                            billing_type="Time & Material",
                            description=description,
                            status="Billed",
                            billing_date=b_date
                        )
                        session.add(new_mb)

        except Exception as e:
            logger.error(f"Error in sync_project_billing_cycles: {str(e)}", exc_info=True)
            raise e

    @staticmethod
    def calculate_task_financials(
        hours_logged: float,
        cost_rate: float,
        billing_rate: float,
        is_non_billable: bool = False
    ) -> Tuple[float, float, float]:
        """
        Calculates internal employee cost, billable revenue amount, and profit/loss
        for a single task entry with zero-value safety guards.
        """
        hours = max(0.0, float(hours_logged or 0.0))
        c_rate = max(0.0, float(cost_rate or 0.0))
        b_rate = 0.0 if is_non_billable else max(0.0, float(billing_rate or 0.0))

        emp_cost = hours * c_rate
        bill_amt = hours * b_rate
        prof_loss = bill_amt - emp_cost
        return emp_cost, bill_amt, prof_loss

    @classmethod
    def evaluate_scheduled_project_billings(cls, session) -> int:
        """
        Evaluates all active projects to see if next_billing_date and next_billing_time
        have passed. If due, creates a ClientReceivables entry, advances next_billing_date,
        and logs an audit notification. Returns the number of triggered billing cycles.
        """
        from src.database.database_tables import Projects, ClientReceivables, AuditLog
        from datetime import timedelta
        import uuid

        triggered_count = 0
        now = datetime.now()

        try:
            billable_projects = session.query(Projects).filter(
                Projects.cost_type.in_(["Monthly Retainer", "Time & Material", "Time and Material", "Hourly Billing"]),
                Projects.next_billing_date != None,
                Projects.next_billing_date != "N/A"
            ).all()

            for proj in billable_projects:
                date_str = proj.next_billing_date.strip() if proj.next_billing_date else ""
                time_str = (proj.next_billing_time or "09:00").strip()

                if not date_str or date_str == "N/A":
                    continue

                # Parse scheduled datetime
                scheduled_dt = None
                for d_fmt in ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"]:
                    try:
                        parsed_d = datetime.strptime(date_str, d_fmt)
                        parsed_t = datetime.strptime(time_str, "%H:%M").time() if ":" in time_str else datetime.strptime("09:00", "%H:%M").time()
                        scheduled_dt = datetime.combine(parsed_d.date(), parsed_t)
                        break
                    except ValueError:
                        continue

                if not scheduled_dt:
                    continue

                # Check if scheduled time has arrived or passed
                if now >= scheduled_dt:
                    amount = float(proj.billing_rate or proj.client_cost or 0.0)
                    cycle_title = f"Scheduled Billing - {proj.name} ({proj.billing_cycle or 'Monthly'})"
                    
                    # Prevent duplicate receivables for the same project and due_date
                    existing_rec = session.query(ClientReceivables).filter_by(
                        project_id=proj.id,
                        due_date=date_str
                    ).first()

                    if not existing_rec:
                        new_rec = ClientReceivables(
                            id=str(uuid.uuid4()),
                            project_id=proj.id,
                            item_name=cycle_title,
                            amount=amount,
                            frequency=proj.billing_cycle or "Monthly",
                            due_date=date_str,
                            is_done=False,
                            created_at=now
                        )
                        session.add(new_rec)
                        triggered_count += 1

                        # Log Audit Entry
                        audit_entry = AuditLog(
                            id=str(uuid.uuid4()),
                            user_id="SYSTEM",
                            action="SCHEDULED_BILLING_TRIGGERED",
                            target_id=proj.id,
                            details=f"Triggered automated billing for project '{proj.name}' (Amount: {amount}, Scheduled: {date_str} {time_str})",
                            timestamp=now
                        )
                        session.add(audit_entry)

                    # Advance next_billing_date to the next cycle
                    recurrence = (proj.billing_cycle or "Monthly").strip()
                    interval_days = proj.billing_interval_days or 30

                    if recurrence == "Yearly":
                        next_dt = scheduled_dt + timedelta(days=365)
                    elif recurrence == "15 Days":
                        next_dt = scheduled_dt + timedelta(days=15)
                    elif recurrence == "Weekly":
                        next_dt = scheduled_dt + timedelta(days=7)
                    elif recurrence == "Hourly":
                        next_dt = scheduled_dt + timedelta(hours=1)
                    else:
                        next_dt = scheduled_dt + timedelta(days=interval_days if interval_days > 0 else 30)

                    proj.next_billing_date = next_dt.strftime("%Y-%m-%d")

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error in evaluate_scheduled_project_billings: {str(e)}", exc_info=True)

        return triggered_count

