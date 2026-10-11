from django.db import models
import re

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9.+_-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+$')


class EmployeeManager(models.Manager):
    def reg_validation(self, formdata):
        errors = {}
        if len(formdata['first_name']) < 2:
            errors['first_name'] = "First name must be at least 2 characters"
        if len(formdata['last_name']) < 2:
            errors['last_name'] = "Last name must be at least 2 characters"
        if not EMAIL_REGEX.match(formdata['email']):
            errors['email'] = "Please enter a valid email"
        elif Employee.objects.filter(email=formdata['email']).exists():
            errors['email_used'] = "This email is already registered"
        if len(formdata['password']) < 8:
            errors['password'] = "Password must be at least 8 characters"
        if formdata['password'] != formdata['confirm_password']:
            errors['confirm_password'] = "Passwords do not match"
        return errors
def login_validation(self, formdata):
        errors = {}
        if len(formdata['email']) == 0:
            errors['email'] = "Email is required"
        if len(formdata['password']) == 0:
            errors['password'] = "Password is required"
        return errors


class Branch(models.Model):
    name = models.CharField(max_length=100)
    ip_address = models.CharField(max_length=45)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Department(models.Model):
    name = models.CharField(max_length=100)
    manager = models.ForeignKey('Employee', related_name='managed_departments',null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Employee(models.Model):
    first_name = models.CharField(max_length=45)
    last_name = models.CharField(max_length=45)
    email = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    job_title = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    is_management = models.BooleanField(default=False)
    department = models.ForeignKey(Department, related_name='employees',null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = EmployeeManager()


class Attendance(models.Model):
    employee = models.ForeignKey(Employee, related_name='attendances', on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, related_name='attendances', on_delete=models.PROTECT)
    date = models.DateField()
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10)  # on_time / late
    late_minutes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveType(models.Model):
    name = models.CharField(max_length=50)  
    hours_per_year = models.IntegerField(null=True, blank=True)
    is_hourly = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LeaveRequest(models.Model):
    employee = models.ForeignKey(Employee, related_name='leave_requests', on_delete=models.CASCADE)
    leave_type = models.ForeignKey(LeaveType, related_name='requests', on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    hours = models.IntegerField() 
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, default='pending') 
    decided_by = models.ForeignKey(Employee, related_name='decisions',null=True, blank=True, on_delete=models.SET_NULL)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)        