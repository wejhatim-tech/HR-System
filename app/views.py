from django.shortcuts import render, redirect
from django.contrib import messages
from . import models
import bcrypt
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import datetime, time

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

    #edit_employee shows the form, and update_employee saves it.