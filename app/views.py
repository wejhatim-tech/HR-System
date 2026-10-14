from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, time
import bcrypt

from .models import *
from . import models

WORK_START = time(8, 0)   # بداية الدوام
GRACE_MINUTES = 10        # مهلة السماح بالدقائق


def index(request):
    if 'user_id' in request.session:
        return redirect('/dashboard')
    return render(request, 'index.html')


def register(request):
    if request.method != 'POST':
        return redirect('/')
    errors = models.Employee.objects.reg_validation(request.POST)
    if len(errors) > 0:
        for key, value in errors.items():
            messages.error(request, value)
        return redirect('/')
    hashed_pw = bcrypt.hashpw(request.POST['password'].encode(), bcrypt.gensalt()).decode()
    employee = models.Employee.objects.create(
        first_name=request.POST['first_name'],
        last_name=request.POST['last_name'],
        email=request.POST['email'],
        password=hashed_pw,
    )
    request.session['user_id'] = employee.id
    return redirect('/dashboard')


def login(request):
    if request.method != 'POST':
        return redirect('/')
    errors = models.Employee.objects.login_validation(request.POST)
    if len(errors) > 0:
        for key, value in errors.items():
            messages.error(request, value)
        return redirect('/')
    employee = models.Employee.objects.filter(email=request.POST['email']).first()
    if not employee or not bcrypt.checkpw(request.POST['password'].encode(), employee.password.encode()):
        messages.error(request, "Invalid email or password")
        return redirect('/')
    request.session['user_id'] = employee.id
    return redirect('/dashboard')


def logout(request):
    request.session.flush()
    return redirect('/')


# الـ IP الحقيقي للمستخدم
def get_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    # على AWS الطلب بيمر من سيرفر وسيط، والـ IP الحقيقي آخر واحد بالقائمة
    if forwarded:
        return forwarded.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR')


def dashboard(request):
    if 'user_id' not in request.session:
        return redirect('/')
    me = models.Employee.objects.get(id=request.session['user_id'])
    today = timezone.localdate()

    # سجل حضوري اليوم (إذا موجود)
    record = models.Attendance.objects.filter(employee=me, date=today).first()

    # الفريق اللي بشوفه: الإدارة كل الموظفين، مدير القسم موظفين قسمه
    team = None
    if me.is_management:
        team = models.Employee.objects.all()
    elif me.managed_departments.exists():
        team = models.Employee.objects.filter(department__manager=me)

    context = {
        'employee': me,
        'today': today,
        'record': record,
        'my_records': me.attendances.order_by('-date')[:5],
    }
    if team is not None:
        today_records = models.Attendance.objects.filter(date=today, employee__in=team).order_by('check_in')
        context['team_total'] = team.count()
        context['today_records'] = today_records
        context['present_count'] = today_records.count()
        context['late_count'] = today_records.filter(status='late').count()
        context['absent_count'] = team.count() - today_records.count()

    # الإشعارات: قرارات على إجازاتي لسا ما شفتها
    unseen = me.leave_requests.exclude(status='pending').filter(is_seen=False)
    context['notifications'] = list(unseen)   # list عشان ناخدهم قبل ما نعلّمهم
    unseen.update(is_seen=True)               # خلص شافهم، ما يرجعوا يطلعوا

    return render(request, 'dashboard.html', context)


# تسجيل الحضور (AJAX)
def check_in(request):
    if 'user_id' not in request.session:
        return JsonResponse({'ok': False, 'msg': 'Please log in first'})
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'msg': 'Invalid request'})
    me = models.Employee.objects.get(id=request.session['user_id'])

    # لازم يكون على شبكة أحد الفروع
    branch = models.Branch.objects.filter(ip_address=get_ip(request)).first()
    if not branch:
        return JsonResponse({'ok': False, 'msg': 'You must be connected to a company branch network'})

    # الوقت من السيرفر، مش من جهاز الموظف
    now = timezone.localtime()
    today = now.date()
    if models.Attendance.objects.filter(employee=me, date=today).exists():
        return JsonResponse({'ok': False, 'msg': 'You already checked in today'})

    # حساب التأخير
    start = datetime.combine(today, WORK_START, tzinfo=now.tzinfo)
    late_minutes = int((now - start).total_seconds() // 60)
    if late_minutes > GRACE_MINUTES:
        status = 'late'
    else:
        status = 'on_time'
        late_minutes = 0

    models.Attendance.objects.create(
        employee=me, branch=branch, date=today,
        check_in=now, status=status, late_minutes=late_minutes,
    )
    if status == 'late':
        sub = 'Late by ' + str(late_minutes) + ' minutes · ' + branch.name
    else:
        sub = 'On time · ' + branch.name
    return JsonResponse({
        'ok': True,
        'title': 'Checked in at ' + now.strftime('%I:%M %p'),
        'sub': sub,
        'next': 'check_out',
        'button': 'Check out',
    })


# تسجيل الانصراف (AJAX)
def check_out(request):
    if 'user_id' not in request.session:
        return JsonResponse({'ok': False, 'msg': 'Please log in first'})
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'msg': 'Invalid request'})
    me = models.Employee.objects.get(id=request.session['user_id'])

    branch = models.Branch.objects.filter(ip_address=get_ip(request)).first()
    if not branch:
        return JsonResponse({'ok': False, 'msg': 'You must be connected to a company branch network'})

    now = timezone.localtime()
    record = models.Attendance.objects.filter(employee=me, date=now.date()).first()
    if not record:
        return JsonResponse({'ok': False, 'msg': 'You have not checked in today'})
    if record.check_out:
        return JsonResponse({'ok': False, 'msg': 'You already checked out today'})

    record.check_out = now
    record.save()
    # مدة الدوام
    worked = int((now - record.check_in).total_seconds() // 60)
    return JsonResponse({
        'ok': True,
        'title': 'Day complete',
        'sub': 'Checked out at ' + now.strftime('%I:%M %p') + ' · worked ' + str(worked // 60) + 'h ' + str(worked % 60) + 'm',
        'next': '',
        'button': '',
    })


def about(request):
    if 'user_id' not in request.session:
        return redirect('/')
    return render(request, 'about.html')


# صفحة الموظفين
def employees(request):
    if 'user_id' not in request.session:
        return redirect('/')
    me = models.Employee.objects.get(id=request.session['user_id'])
    # الموظف العادي ما بيشوف هاي الصفحة
    if not me.is_management and not me.managed_departments.exists():
        return redirect('/dashboard')
    employee_list = models.Employee.objects.all().order_by('first_name')
    # مدير القسم بيشوف موظفين قسمه بس
    if not me.is_management:
        employee_list = employee_list.filter(department__manager=me)
    # البحث بالاسم أو المسمى الوظيفي
    search = request.GET.get('search', '')
    if search:
        employee_list = employee_list.filter(
            Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(job_title__icontains=search)
        )

    # الفلتر حسب القسم
    selected_dept = request.GET.get('department', '')
    if selected_dept:
        employee_list = employee_list.filter(department_id=selected_dept)

    context = {
        'me': me,
        'employees': employee_list,
        'departments': models.Department.objects.all(),
        'search': search,
        'selected_dept': int(selected_dept) if selected_dept else 0,
    }
    return render(request, 'employees.html', context)


# edit_employee بيعرض الفورم، و update_employee بيحفظه
def edit_employee(request, id):
    if 'user_id' not in request.session:
        return redirect('/')
    me = models.Employee.objects.get(id=request.session['user_id'])
    if not me.is_management:
        return redirect('/employees')
    context = {
        'employee': models.Employee.objects.get(id=id),
        'departments': models.Department.objects.all(),
    }
    return render(request, 'edit_employee.html', context)


def update_employee(request, id):
    if 'user_id' not in request.session:
        return redirect('/')
    if request.method != 'POST':
        return redirect('/employees')
    me = models.Employee.objects.get(id=request.session['user_id'])
    if not me.is_management:
        return redirect('/employees')

    errors = models.Employee.objects.update_validation(request.POST)
    if len(errors) > 0:
        for key, value in errors.items():
            messages.error(request, value)
        return redirect('/employees/' + str(id) + '/edit')

    employee = models.Employee.objects.get(id=id)
    employee.job_title = request.POST['job_title']
    employee.phone = request.POST['phone']
    employee.hire_date = request.POST['hire_date'] or None
    employee.department_id = request.POST['department'] or None
    employee.is_management = 'is_management' in request.POST
    employee.save()

    models.Department.objects.filter(manager=employee).exclude(id=employee.department_id).update(manager=None)
    if employee.department:
        if 'is_manager' in request.POST:
            employee.department.manager = employee
            employee.department.save()
        elif employee.department.manager_id == employee.id:
            employee.department.manager = None
            employee.department.save()
    return redirect('/employees')


# ===================== الإجازات =====================

# مين مسموحله يوافق على طلب
def can_decide(me, leave):
    emp = leave.employee
    if emp.id == me.id:
        return False
    # مدير قسم، أو إدارة، أو قسمه بدون مدير ← الإدارة بتقرر
    if emp.is_management or emp.managed_departments.exists() or not emp.department or not emp.department.manager:
        return me.is_management
    # موظف عادي ← مدير قسمه
    return emp.department.manager.id == me.id


def leaves(request):
    if 'user_id' not in request.session:
        return redirect('/')
    me = Employee.objects.get(id=request.session['user_id'])

    # كروت الرصيد (الأنواع اللي إلها رصيد سنوي بس)
    balances = []
    for t in LeaveType.objects.filter(hours_per_year__isnull=False):
        used = used_hours(me, t, ['approved'])
        pending = used_hours(me, t, ['pending'])
        balances.append({
            'name': t.name,
            'total': hours_text(t.hours_per_year),
            'used': hours_text(used),
            'pending': hours_text(pending) if pending else '',
            'remaining': hours_text(t.hours_per_year - used),
        })

    # الطلبات اللي بستناني أوافق عليها (للمدراء والإدارة بس)
    to_approve = None
    if me.is_management or me.managed_departments.exists():
        to_approve = []
        for r in LeaveRequest.objects.filter(status='pending').exclude(employee=me).order_by('created_at'):
            if can_decide(me, r):
                to_approve.append(r)

    context = {
        'me': me,
        'balances': balances,
        'leave_types': LeaveType.objects.all(),
        'my_requests': me.leave_requests.order_by('-created_at'),
        'to_approve': to_approve,
    }
    return render(request, 'leaves.html', context)


def add_leave(request):
    if 'user_id' not in request.session:
        return redirect('/')
    if request.method != 'POST':
        return redirect('/leaves')
    me = Employee.objects.get(id=request.session['user_id'])

    errors = LeaveRequest.objects.leave_validation(request.POST, me)
    if errors:
        for key, value in errors.items():
            messages.error(request, value)
        return redirect('/leaves')

    leave_type = LeaveType.objects.get(id=request.POST['leave_type'])
    start = request.POST['start_date']
    if leave_type.is_hourly:
        end = start
        start_time = request.POST['start_time']
        end_time = request.POST['end_time']
    else:
        end = request.POST['end_date']
        start_time = None
        end_time = None

    LeaveRequest.objects.create(
        employee=me,
        leave_type=leave_type,
        start_date=start,
        end_date=end,
        start_time=start_time,
        end_time=end_time,
        hours=calc_hours(request.POST, leave_type),
        reason=request.POST.get('reason', ''),
    )
    messages.success(request, 'Your leave request was sent')
    return redirect('/leaves')


# الموافقة أو الرفض (AJAX)
def decide_leave(request, id):
    if 'user_id' not in request.session:
        return JsonResponse({'ok': False, 'msg': 'Please log in first'})
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'msg': 'Invalid request'})
    me = Employee.objects.get(id=request.session['user_id'])

    leave = LeaveRequest.objects.filter(id=id).first()
    if not leave or leave.status != 'pending':
        return JsonResponse({'ok': False, 'msg': 'This request was already decided'})
    if not can_decide(me, leave):
        return JsonResponse({'ok': False, 'msg': 'You are not allowed to decide this request'})

    action = request.POST.get('action')
    if action not in ['approved', 'rejected']:
        return JsonResponse({'ok': False, 'msg': 'Invalid action'})

    leave.status = action
    leave.decided_by = me
    leave.decided_at = timezone.now()
    leave.is_seen = False      # الموظف لسا ما شاف القرار ← بيطلعله إشعار على الـ Dashboard
    leave.save()
    return JsonResponse({'ok': True, 'status': action})