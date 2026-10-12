from django.shortcuts import render, redirect
from django.contrib import messages
from . import models
import bcrypt
from django.db.models import Q


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


def dashboard(request):
    if 'user_id' not in request.session:
        return redirect('/')
    context = {
        'employee': models.Employee.objects.get(id=request.session['user_id']),
    }
    return render(request, 'dashboard.html', context)

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