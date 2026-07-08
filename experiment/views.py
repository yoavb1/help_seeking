from django.http import JsonResponse
from .models import ChoiceExperimentSession, ParticipantTrial
import json
from django.urls import reverse
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Avg, Sum, Q


def onboarding_view(request):
    """Handles the 5-screen onboarding sequence."""
    if 'experiment_sid' not in request.session:
        import random
        assigned_condition = random.choice(['prestige', 'dominance'])
        new_session = ChoiceExperimentSession.objects.create(condition=assigned_condition)
        request.session['experiment_sid'] = str(new_session.session_id)
        request.session['onboarding_step'] = 1

    session_id = request.session.get('experiment_sid')
    experiment_session = get_object_or_404(ChoiceExperimentSession, session_id=session_id)

    if request.method == "POST":
        current_step = request.session.get('onboarding_step', 1)
        if current_step >= 5:
            # Onboarding finished! Redirect straight to dashboard for practice run
            return redirect('experiment:practice_run')
        else:
            request.session['onboarding_step'] = current_step + 1
            return redirect('experiment:onboarding')

    step = request.session.get('onboarding_step', 1)
    return render(request, 'experiment/onboarding.html', {
        'step': step,
        'condition': experiment_session.condition
    })


def practice_run_view(request):
    """Loads the dashboard layout configured as an unlogged 5-trial practice run."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(ChoiceExperimentSession, session_id=session_id)

    context = {
        'session': session,
        'is_practice': True,  # 🌟 CRITICAL FLAG: Tells JavaScript this is a practice run
        'max_trials': 2,  # Short practice session length
    }
    return render(request, 'experiment/dashboard.html', context)


def ready_alert_view(request):
    """Intermediate warning screen confirming that practice is over."""
    if request.method == "POST":
        return redirect('experiment:dashboard')
    return render(request, 'experiment/ready_alert.html')


def dashboard_view(request):
    """Loads the dashboard layout configured as the live 50-trial experiment."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(ChoiceExperimentSession, session_id=session_id)

    context = {
        'session': session,
        'is_practice': False,  # 🌟 CRITICAL FLAG: Tells JavaScript this counts!
        'max_trials': 5,  # Full experiment task length
    }
    return render(request, 'experiment/dashboard.html', context)


def submit_task(request):
    """Processes the final array stack of 50 trials asynchronously via AJAX."""
    if request.method == "POST":
        session_id = request.session.get('experiment_sid')
        session = get_object_or_404(ChoiceExperimentSession, session_id=session_id)

        try:
            data = json.loads(request.body)
            trials_data = data.get('trials', [])

            total_score = 0
            total_help = 0
            human_cnt = 0
            ai_cnt = 0

            # Inside your submit_task view function in views.py:
            for t in trials_data:
                is_correct = t.get('is_correct', False)
                help_choice = t.get('help_chosen', 'none')

                if is_correct:
                    total_score += 100
                if help_choice != 'none':
                    total_help += 1
                if help_choice == 'human':
                    human_cnt += 1
                elif help_choice == 'ai':
                    ai_cnt += 1

                # WRITE THE INDIVIDUAL TRIAL DATA MATRIX LOG WITH RUNNING SCORE
                ParticipantTrial.objects.create(
                    session=session,
                    trial_number=t.get('trial_number'),
                    difficulty=t.get('difficulty'),
                    help_chosen=help_choice,
                    reaction_time=t.get('reaction_time', 0.0),
                    is_correct=is_correct,
                    running_score=t.get('running_score', 0)  # SAVE LOG DIRECTLY HERE
                )

            # Save aggregated variables back onto parent session row
            session.total_score = total_score
            session.total_help_sought = total_help
            session.human_clicks = human_cnt
            session.ai_clicks = ai_cnt
            session.save()

            return JsonResponse({
                'status': 'success',
                'redirect_url': reverse('experiment:survey')
            })

        except Exception as e:
            # Captures database or JSON data processing errors cleanly
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return redirect('experiment:dashboard')


def survey_view(request):
    """Page 1: Handles capturing the mediation metrics (Likert Scales)."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(ChoiceExperimentSession, session_id=session_id)

    if request.method == "POST":
        image_cost = request.POST.get('image_cost')
        closeness = request.POST.get('closeness')

        # Save Page 1 metrics
        session.image_cost_rating = int(image_cost) if image_cost else None
        session.closeness_rating = int(closeness) if closeness else None
        session.save()

        # Redirect seamlessly to Page 2
        return redirect('experiment:demographics')

    return render(request, 'experiment/survey.html')


def demographics_view(request):
    """Page 2: Handles capturing age and gender diagnostics."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(ChoiceExperimentSession, session_id=session_id)

    if request.method == "POST":
        age = request.POST.get('age')
        gender = request.POST.get('gender')

        # Save Page 2 metrics
        session.participant_age = int(age) if age else None
        session.participant_gender = gender
        session.save()

        # All done! Move to the final landing screen
        return redirect('experiment:thank_you')

    return render(request, 'experiment/demographics.html')

def thank_you_view(request):
    """Final study debrief and terminal termination endpoint."""
    # Clean the session token so refreshing doesn't corrupt data pipelines
    if 'experiment_sid' in request.session:
        del request.session['experiment_sid']
    return render(request, 'experiment/thank_you.html')


@staff_member_required
def admin_analytics_dashboard(request):
    # 1. Grab filter parameters from the request
    condition_filter = request.GET.get('condition', '')
    gender_filter = request.GET.get('gender', '')

    # Base Queryset
    sessions = ChoiceExperimentSession.objects.all()

    # Apply Filters if selected
    if condition_filter:
        sessions = sessions.filter(condition=condition_filter)
    if gender_filter:
        sessions = sessions.filter(participant_gender=gender_filter)

    # 2. Distribution Breakdown (Total participants per condition)
    condition_counts = ChoiceExperimentSession.objects.values('condition').annotate(
        total=Count('id')
    ).order_by('condition')  # <-- Fixed here!

    # 3. Aggregated Statistical Calculations
    stats = sessions.aggregate(
        total_participants=Count('id'),
        avg_help_sought=Avg('total_help_sought'),
        total_human_clicks=Sum('human_clicks'),
        total_ai_clicks=Sum('ai_clicks'),
        avg_image_cost=Avg('image_cost_rating'),
        avg_closeness=Avg('closeness_rating'),
        avg_age=Avg('participant_age')
    )

    # 4. Extract distinct criteria for filtering dropdowns
    distinct_conditions = ChoiceExperimentSession.objects.values_list('condition', flat=True).distinct()
    distinct_genders = ChoiceExperimentSession.objects.values_list('participant_gender', flat=True).distinct().exclude(
        participant_gender__isnull=True)

    context = {
        'sessions': sessions,
        'condition_counts': condition_counts,
        'stats': stats,
        'distinct_conditions': distinct_conditions,
        'distinct_genders': distinct_genders,
        'selected_condition': condition_filter,
        'selected_gender': gender_filter,
    }
    return render(request, 'experiment/admin_analytics.html', context)