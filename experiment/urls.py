from django.urls import path
from . import views

app_name = 'experiment'

urlpatterns = [
    path('', views.onboarding_view, name='onboarding'),
    path('practice-run/', views.practice_run_view, name='practice_run'),  # Practice Route
    path('get-ready/', views.ready_alert_view, name='ready_alert'),  # Transition Screen
    path('dashboard/', views.dashboard_view, name='dashboard'),  # Live Experiment Route

    # Task Submission & Survey Handlers
    path('submit-trial/', views.submit_trial, name='submit_trial'),
    path('submit-task/', views.submit_task, name='submit_task'),
    path('survey/', views.survey_view, name='survey'),
    path('demographics/', views.demographics_view, name='demographics'),
    path('thank-you/', views.thank_you_view, name='thank_you'),
    path('export/trials-csv/',views.download_trials_csv, name="download_trials_csv",),
    path('admin-dashboard/', views.analytics_dashboard, name='analytics_dashboard'),
    path('admin-dashboard/', views.analytics_dashboard, name='analytics_dashboard'),
    path('admin-dashboard/clear-data/', views.clear_all_experiment_data, name='clear_all_experiment_data'),
]