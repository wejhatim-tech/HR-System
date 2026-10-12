from django.contrib import admin
from . import models

admin.site.register(models.Employee)
admin.site.register(models.Department)
admin.site.register(models.Branch)
admin.site.register(models.LeaveType)
admin.site.register(models.Attendance)
admin.site.register(models.LeaveRequest)