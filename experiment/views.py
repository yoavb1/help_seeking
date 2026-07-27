import json
import os
import random
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import HttpResponse
import csv

from .models import ChoiceExperimentSession, ParticipantTrial

# 💡 Set your Prolific Completion Code here:
PROLIFIC_COMPLETION_CODE = "C1234XYZ"


def load_and_shuffle_questions(count, filename='questions.json', difficulty=None):
    """Utility to load questions from JSON, map difficulty codes (E/M/H), and shuffle."""
    json_path = os.path.join(
        settings.BASE_DIR, 'experiment', 'data', filename
    )

    if not os.path.exists(json_path):
        return []

    with open(json_path, 'r', encoding='utf-8') as f:
        all_questions = json.load(f)

    # Normalize requested difficulty filter to JSON single-letter code
    if difficulty:
        diff_map = {'easy': 'E', 'medium': 'M', 'hard': 'H', 'E': 'E', 'M': 'M', 'H': 'H'}
        target_diff = diff_map.get(str(difficulty).lower(), str(difficulty).upper())
        all_questions = [
            q for q in all_questions if q.get('difficulty') == target_diff
        ]

    if not all_questions:
        return []

    random.shuffle(all_questions)

    selected_questions = []
    for i in range(count):
        q = dict(all_questions[i % len(all_questions)])
        q['number'] = i + 1  # Assign trial number 1..N
        selected_questions.append(q)

    return selected_questions


def onboarding_view(request):
    """Handles initial participant entry, Prolific ID capture, and onboarding."""
    if 'experiment_sid' not in request.session:
        assigned_condition = random.choice(['prestige', 'dominance'])
        if assigned_condition == 'dominance':
            style = 'Leads with an assertive and forceful approach, taking direct control over decisions and group behavior.' if assigned_condition == 'Dominance' else '' if assigned_condition == 'Prestige' else ''
        elif assigned_condition == 'prestige':
            style = 'Leads through respect and admiration, sharing valuable knowledge, skills, and expertise.'
        else:
            style = ''

        # Capture Prolific parameters from GET query string
        prolific_pid = request.GET.get('PROLIFIC_PID', None)
        study_id = request.GET.get('STUDY_ID', None)
        prolific_session_id = request.GET.get('SESSION_ID', None)

        new_session = ChoiceExperimentSession.objects.create(
            condition=assigned_condition,
            prolific_pid=prolific_pid,
            study_id=study_id,
            prolific_session_id=prolific_session_id,
        )
        request.session['experiment_sid'] = str(new_session.session_id)
        request.session['onboarding_step'] = 1
        request.session['style'] = style

    session_id = request.session.get('experiment_sid')
    experiment_session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    if request.method == "POST":
        current_step = request.session.get('onboarding_step', 1)
        if current_step >= 6:
            # Onboarding finished! Redirect to dashboard for practice run
            return redirect('experiment:practice_run')
        else:
            request.session['onboarding_step'] = current_step + 1
            return redirect('experiment:onboarding')

    step = request.session.get('onboarding_step', 1)
    return render(
        request,
        'experiment/onboarding.html',
        {'step': step, 'condition': experiment_session.condition},
    )


def practice_run_view(request):
    """Loads the dashboard layout configured as an unlogged practice run with dynamic questions."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    max_trials = getattr(settings, 'EXPERIMENT_PRACTICE_TRIALS', 5)
    questions = load_and_shuffle_questions(count=max_trials, filename='questions_practice.json')

    context = {
        'session': session,
        'style': request.session['style'],
        'is_practice': True,
        'max_trials': max_trials,
        'questions_json': json.dumps(questions),  # Passed as JSON string
    }

    return render(request, 'experiment/dashboard.html', context)


def ready_alert_view(request):
    """Intermediate warning screen confirming that practice is over."""
    if request.method == "POST":
        return redirect('experiment:dashboard')
    return render(request, 'experiment/ready_alert.html')


def dashboard_view(request):
    """Loads the dashboard layout configured as the live experiment with dynamic questions."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    max_trials = getattr(settings, 'EXPERIMENT_LIVE_TRIALS', 50)
    questions = load_and_shuffle_questions(count=max_trials, filename='questions_live.json')

    context = {
        'session': session,
        'is_practice': False,
        'style': request.session['style'],
        'max_trials': max_trials,
        'time_per_trial': getattr(settings, 'TIME_LIMIT', 20),
        'questions_json': json.dumps(questions),  # Passed as JSON string
    }
    return render(request, 'experiment/dashboard.html', context)


def submit_trial(request):
    """Processes a single trial result asynchronously after each screen."""
    if request.method == "POST":
        session_id = request.session.get("experiment_sid")
        session = get_object_or_404(
            ChoiceExperimentSession, session_id=session_id
        )

        try:
            # Parse the single trial dictionary sent from JS
            t = json.loads(request.body)

            diff_map = {
                "EASY": "E",
                "MEDIUM": "M",
                "HARD": "H",
                "E": "E",
                "M": "M",
                "H": "H",
            }
            raw_diff = str(t.get("difficulty", "E")).upper()
            diff_code = diff_map.get(raw_diff, "E")

            is_correct = t.get("is_correct", False)
            help_choice = t.get("help_chosen", "none")
            advisor_role = t.get("advisor_role", "none")

            # 1. Save THIS trial immediately to the DB
            ParticipantTrial.objects.create(
                session=session,
                trial_number=t.get("trial_number"),
                difficulty=diff_code,
                help_chosen=help_choice,
                advisor_role=advisor_role,
                reaction_time=t.get("reaction_time", 0.0),
                is_correct=is_correct,
                running_score=t.get("running_score", 0),
            )

            # 2. Increment parent session metrics incrementally
            if is_correct:
                session.total_score = (session.total_score or 0) + 100
            if help_choice != "none":
                session.total_help_sought = (session.total_help_sought or 0) + 1
            if help_choice == "human":
                session.human_clicks = (session.human_clicks or 0) + 1
            elif help_choice == "ai":
                session.ai_clicks = (session.ai_clicks or 0) + 1

            session.save()

            return JsonResponse({"status": "success", "message": "Trial logged"})

        except Exception as e:
            return JsonResponse(
                {"status": "error", "message": str(e)}, status=400
            )

    return JsonResponse({"status": "invalid method"}, status=405)


def submit_task(request):
    """Processes trial results asynchronously via AJAX."""
    if request.method == "POST":
        session_id = request.session.get('experiment_sid')
        session = get_object_or_404(
            ChoiceExperimentSession, session_id=session_id
        )

        try:
            data = json.loads(request.body)
            trials_data = data.get('trials', [])

            total_score = 0
            total_help = 0
            human_cnt = 0
            ai_cnt = 0

            # Mapping table to handle E, M, H alongside full string names
            diff_map = {
                'EASY': 'E', 'MEDIUM': 'M', 'HARD': 'H',
                'E': 'E', 'M': 'M', 'H': 'H'
            }

            trial_objects = []

            for t in trials_data:
                is_correct = t.get('is_correct', False)
                help_choice = t.get('help_chosen', 'none')
                advisor_role = t.get('advisor_role', 'none')

                # Normalize difficulty code safely
                raw_diff = str(t.get('difficulty', 'E')).upper()
                diff_code = diff_map.get(raw_diff, 'E')

                # Tally metrics
                if is_correct:
                    total_score += 100
                if help_choice != 'none':
                    total_help += 1
                if help_choice == 'human':
                    human_cnt += 1
                elif help_choice == 'ai':
                    ai_cnt += 1

                # Build model instance for bulk insert
                trial_objects.append(
                    ParticipantTrial(
                        session=session,
                        trial_number=t.get('trial_number'),
                        difficulty=diff_code,
                        help_chosen=help_choice,
                        advisor_role=advisor_role,
                        reaction_time=t.get('reaction_time', 0.0),
                        is_correct=is_correct,
                        running_score=t.get('running_score', 0),
                    )
                )

            # Save all trials in a single DB query
            ParticipantTrial.objects.bulk_create(trial_objects)

            # Update aggregated metrics on parent session
            session.total_score = total_score

            session.total_help_sought = total_help
            session.human_clicks = human_cnt
            session.ai_clicks = ai_cnt
            session.save()

            return JsonResponse(
                {
                    'status': 'success',
                    'redirect_url': reverse('experiment:survey'),
                }
            )

        except Exception as e:
            return JsonResponse(
                {'status': 'error', 'message': str(e)}, status=400
            )

    return redirect('experiment:dashboard')


def survey_view(request):
    """Handles capturing the updated Likert survey evaluation metrics."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    if request.method == "POST":
        status_reduction = request.POST.get('status_reduction')
        incompetent = request.POST.get('incompetent')
        inexperienced = request.POST.get('inexperienced')
        lesser = request.POST.get('lesser')
        org_status_hurt = request.POST.get('org_status_hurt')
        held_against = request.POST.get('held_against')

        session.status_reduction = (
            int(status_reduction) if status_reduction else None
        )
        session.incompetent_rating = int(incompetent) if incompetent else None
        session.inexperienced_rating = (
            int(inexperienced) if inexperienced else None
        )
        session.lesser_rating = int(lesser) if lesser else None
        session.org_status_hurt_rating = (
            int(org_status_hurt) if org_status_hurt else None
        )
        session.held_against_rating = (
            int(held_against) if held_against else None
        )
        session.save()

        return redirect('experiment:demographics')

    return render(request, 'experiment/survey.html')


def demographics_view(request):
    """Handles capturing age and gender diagnostics."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    if request.method == "POST":
        age = request.POST.get('age')
        gender = request.POST.get('gender')

        session.participant_age = int(age) if age else None
        session.participant_gender = gender
        session.save()

        return redirect('experiment:thank_you')

    return render(request, 'experiment/demographics.html')


def thank_you_view(request):
    """Final study debrief screen providing the Prolific completion link."""
    session_id = request.session.get('experiment_sid')
    session = (
        ChoiceExperimentSession.objects.filter(session_id=session_id).first()
        if session_id
        else None
    )

    prolific_redirect_url = f"https://app.prolific.com/submissions/complete?cc={PROLIFIC_COMPLETION_CODE}"

    if 'experiment_sid' in request.session:
        del request.session['experiment_sid']

    context = {
        'completion_code': PROLIFIC_COMPLETION_CODE,
        'prolific_redirect_url': prolific_redirect_url,
        'session': session,
    }
    return render(request, 'experiment/thank_you.html', context)

def admin_dashboard(request):
    trials = ParticipantTrial.objects.select_related("session").all()

    # Calculate summary metrics
    total_count = trials.count()
    correct_count = trials.filter(is_correct=True).count()
    accuracy_rate = (
        round((correct_count / total_count) * 100, 1) if total_count > 0 else 0
    )

    avg_rt = trials.aggregate(Avg("reaction_time"))["reaction_time__avg"]
    avg_rt = round(avg_rt, 2) if avg_rt else 0

    ai_count = trials.filter(help_chosen="ai").count()
    ai_usage_rate = (
        round((ai_count / total_count) * 100, 1) if total_count > 0 else 0
    )

    context = {
        "trials": trials,
        "accuracy_rate": accuracy_rate,
        "avg_rt": avg_rt,
        "ai_usage_rate": ai_usage_rate,
    }
    return render(request, "admin_dashboard.html", context)


@staff_member_required
# @staff_member_required  # Optional: Restrict access to logged-in admin users only
def analytics_dashboard(request):
    trials = ParticipantTrial.objects.select_related('session').all()

    # Calculate top summary metrics
    total_count = trials.count()
    correct_count = trials.filter(is_correct=True).count()
    accuracy_rate = round((correct_count / total_count) * 100, 1) if total_count > 0 else 0

    avg_rt = trials.aggregate(Avg('reaction_time'))['reaction_time__avg']
    avg_rt = round(avg_rt, 2) if avg_rt else 0

    ai_count = trials.filter(help_chosen='ai').count()
    ai_usage_rate = round((ai_count / total_count) * 100, 1) if total_count > 0 else 0

    context = {
        'trials': trials,
        'accuracy_rate': accuracy_rate,
        'avg_rt': avg_rt,
        'ai_usage_rate': ai_usage_rate,
    }
    return render(request, 'admin_dashboard.html', context)


def download_trials_csv(request):
    # 1. Set response headers for file download
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="participant_trials_data.csv"'
    )

    writer = csv.writer(response)

    # 2. Header row
    writer.writerow([
        "Session ID",
        "Condition",
        "Trial Number",
        "Difficulty",
        "Help Chosen",
        "Advisor Role",
        "Reaction Time (s)",
        "Is Correct",
        "Running Score",
    ])

    # 3. Fetch all trials from database
    trials = ParticipantTrial.objects.select_related("session").all()

    # 4. Write row for each trial
    for t in trials:
        # Get condition safely from parent session (handling fallback names)
        session_id = t.session.session_id if t.session else "N/A"
        condition = (
            getattr(t.session, "condition", "N/A") if t.session else "N/A"
        )

        writer.writerow([
            session_id,
            condition,
            t.trial_number,
            t.difficulty,
            t.help_chosen,
            t.advisor_role,
            t.reaction_time,
            t.is_correct,
            t.running_score,
        ])

    return response