from django.db import models
import re
from datetime import date, datetime, timedelta

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9.+_-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+$')


class EmployeeManager(models.Manager):
    def reg_validation(self, formdata):
        errors = {}
        if len(formdata.get('first_name', '')) < 2:
            errors['first_name'] = 'First name must be at least 2 characters'
        if len(formdata.get('last_name', '')) < 2:
            errors['last_name'] = 'Last name must be at least 2 characters'
        if not EMAIL_REGEX.match(formdata.get('email', '')):
            errors['email'] = 'Invalid email address'
        elif Employee.objects.filter(email=formdata['email']).exists():
            errors['email'] = 'This email is already registered'
        if len(formdata.get('password', '')) < 8:
            errors['password'] = 'Password must be at least 8 characters'
        if formdata.get('password') != formdata.get('confirm_password'):
            errors['confirm_password'] = 'Passwords do not match'
        return errors

    def login_validation(self, formdata):
        errors = {}
        if not formdata.get('email'):
            errors['email'] = 'Email is required'
        if not formdata.get('password'):
            errors['password'] = 'Password is required'
        return errors

    def update_validation(self, formdata):
        errors = {}
        job_title = formdata.get('job_title', '')
        phone = formdata.get('phone', '')
        hire_date = formdata.get('hire_date', '')
        if job_title and len(job_title) < 2:
            errors['job_title'] = 'Job title must be at least 2 characters'
        if phone and (not phone.isdigit() or len(phone) < 9 or len(phone) > 15):
            errors['phone'] = 'Phone must be 9 to 15 digits'
        if hire_date and hire_date > str(date.today()):
            errors['hire_date'] = 'Hire date cannot be in the future'
        return errors


class LeaveRequestManager(models.Manager):
    def leave_validation(self, formdata, employee):
        errors = {}
        # نوع الإجازة
        leave_type = LeaveType.objects.filter(id=formdata.get('leave_type') or 0).first()
        if not leave_type:
            errors['leave_type'] = 'Please choose a leave type'
            return errors
        # تاريخ البداية
        if not formdata.get('start_date'):
            errors['start_date'] = 'Start date is required'
            return errors
        if formdata['start_date'] < str(date.today()):
            errors['start_date'] = 'Start date cannot be in the past'
            return errors
        # المغادرة: لازم وقت من وإلى
        if leave_type.is_hourly:
            if not formdata.get('start_time') or not formdata.get('end_time'):
                errors['time'] = 'From and to time are required for short leave'
                return errors
            if formdata['end_time'] <= formdata['start_time']:
                errors['time'] = 'End time must be after start time'
                return errors
            if date.fromisoformat(formdata['start_date']).weekday() == 4:
                errors['start_date'] = 'Friday is a day off'
                return errors
        # الإجازة العادية: لازم تاريخ نهاية
        else:
            if not formdata.get('end_date'):
                errors['end_date'] = 'End date is required'
                return errors
            if formdata['end_date'] < formdata['start_date']:
                errors['end_date'] = 'End date must be after start date'
                return errors
        # نحسب الساعات
        hours = calc_hours(formdata, leave_type)
        if hours == 0:
            errors['hours'] = 'The selected days are all Fridays'
            return errors
        if leave_type.is_hourly and hours > 8:
            errors['hours'] = 'Short leave cannot be more than 8 hours'
            return errors
        # الرصيد (المغادرة بتنخصم من السنوية)
        main_type = balance_type(leave_type)
        if main_type and main_type.hours_per_year:
            available = main_type.hours_per_year - used_hours(employee, main_type, ['approved', 'pending'])
            if hours > available:
                errors['balance'] = f'Not enough {main_type.name} balance. Available: {hours_text(available)}'
        return errors


class Branch(models.Model):
    name = models.CharField(max_length=255)
    ip_address = models.CharField(max_length=45)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=255)
    manager = models.ForeignKey('Employee', related_name='managed_departments', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Employee(models.Model):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    job_title = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    is_management = models.BooleanField(default=False)
    department = models.ForeignKey(Department, related_name='employees', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = EmployeeManager()

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class Attendance(models.Model):
    employee = models.ForeignKey(Employee, related_name='attendances', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='attendances', on_delete=models.PROTECT)
    date = models.DateField()
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10)          # on_time / late
    late_minutes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveType(models.Model):
    name = models.CharField(max_length=255)
    hours_per_year = models.IntegerField(null=True, blank=True)
    is_hourly = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class LeaveRequest(models.Model):
    employee = models.ForeignKey(Employee, related_name='leave_requests', on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, related_name='requests', on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    hours = models.IntegerField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, default='pending')   # pending / approved / rejected
    decided_by = models.ForeignKey(Employee, related_name='decisions', null=True, blank=True, on_delete=models.SET_NULL)
    decided_at = models.DateTimeField(null=True, blank=True)
    is_seen = models.BooleanField(default=False)   # جديد: هل الموظف شاف القرار؟
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = LeaveRequestManager()


# ===== دوال مساعدة =====

# عدد أيام الدوام بين تاريخين (الجمعة عطلة)
def working_days(start, end):
    days = 0
    current = start
    while current <= end:
        if current.weekday() != 4:   # 4 = الجمعة
            days += 1
        current += timedelta(days=1)
    return days


# كم ساعة الطلب
def calc_hours(formdata, leave_type):
    start = date.fromisoformat(formdata['start_date'])
    if leave_type.is_hourly:
        t1 = datetime.strptime(formdata['start_time'], '%H:%M')
        t2 = datetime.strptime(formdata['end_time'], '%H:%M')
        minutes = int((t2 - t1).total_seconds() // 60)
        return (minutes + 59) // 60     # نقرّب لفوق: ساعة ونص = 2 ساعات
    end = date.fromisoformat(formdata['end_date'])
    return working_days(start, end) * 8


# المغادرة بتنخصم من رصيد السنوية
def balance_type(leave_type):
    if leave_type.is_hourly:
        return LeaveType.objects.filter(name__icontains='annual').first()
    return leave_type


# مجموع الساعات المستخدمة من نوع معين
def used_hours(employee, leave_type, statuses):
    types = [leave_type]
    if 'annual' in leave_type.name.lower():
        types += list(LeaveType.objects.filter(is_hourly=True))
    total = 0
    for r in employee.leave_requests.filter(leave_type__in=types, status__in=statuses):
        total += r.hours
    return total


# 20 ساعة ← "2d 4h"
def hours_text(hours):
    days = hours // 8
    rest = hours % 8
    if rest:
        return f'{days}d {rest}h'
    return f'{days}d'