from django.shortcuts import render, redirect
from django.contrib import messages
from . import models
import bcrypt


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
