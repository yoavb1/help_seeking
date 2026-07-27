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
from django.db import transaction
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
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


from django.shortcuts import render, redirect
import random
from .models import ChoiceExperimentSession


def onboarding_view(request):
    """Handles initial participant entry, Prolific ID capture, and onboarding."""

    # 1. Safely retrieve the session ID from the user's browser session
    session_id = request.session.get('experiment_sid')
    experiment_session = None

    if session_id:
        try:
            experiment_session = ChoiceExperimentSession.objects.get(session_id=session_id)
        except ChoiceExperimentSession.DoesNotExist:
            # Session was deleted in DB (e.g. reset button), clear stale session data
            request.session.pop('experiment_sid', None)
            request.session.pop('onboarding_step', None)
            request.session.pop('style', None)
            experiment_session = None

    # 2. Create a new session if none exists
    if not experiment_session:
        assigned_condition = random.choice(['prestige', 'dominance'])
        if assigned_condition == 'dominance':
            style = 'Leads with an assertive and forceful approach, taking direct control over decisions and group behavior.'
        else:
            style = 'Leads through respect and admiration, sharing valuable knowledge, skills, and expertise.'

        # Capture Prolific parameters from GET query string
        prolific_pid = request.GET.get('PROLIFIC_PID', None)
        study_id = request.GET.get('STUDY_ID', None)
        prolific_session_id = request.GET.get('SESSION_ID', None)

        experiment_session = ChoiceExperimentSession.objects.create(
            condition=assigned_condition,
            prolific_pid=prolific_pid,
            study_id=study_id,
            prolific_session_id=prolific_session_id,
        )

        request.session['experiment_sid'] = str(experiment_session.session_id)
        request.session['onboarding_step'] = 1
        request.session['style'] = style

    # 3. Handle Form Submissions (POST requests)
    if request.method == "POST":
        current_step = request.session.get('onboarding_step', 1)
        if current_step == 6:
            item_1 = request.POST.get('mc_item_1')
            item_2 = request.POST.get('mc_item_2')
            item_3 = request.POST.get('mc_item_3')
            item_4 = request.POST.get('mc_item_4')
            item_5 = request.POST.get('mc_item_5')
            item_6 = request.POST.get('mc_item_6')
            item_7 = request.POST.get('mc_item_7')
            item_8 = request.POST.get('mc_item_8')
            attn_check = request.POST.get('mc_attention_check')

            # Save Likert ratings
            experiment_session.mc_item_1_respect = int(item_1) if item_1 else None
            experiment_session.mc_item_2_control_others = int(item_2) if item_2 else None
            experiment_session.mc_item_3_aggressive_tactics = int(item_3) if item_3 else None
            experiment_session.mc_item_4_high_esteem = int(item_4) if item_4 else None
            experiment_session.mc_item_5_control_vs_controlled = int(item_5) if item_5 else None
            experiment_session.mc_item_6_way_with_others = int(item_6) if item_6 else None
            experiment_session.mc_item_7_talents_recognized = int(item_7) if item_7 else None
            experiment_session.mc_item_8_seek_advice = int(item_8) if item_8 else None

            # Validate Attention Check (Participant must choose option '2')
            if attn_check:
                experiment_session.mc_attention_check_value = int(attn_check)
                experiment_session.passed_attention_check = (int(attn_check) == 2)

            experiment_session.save()

            # Onboarding finished! Redirect to practice run
            return redirect('experiment:practice_run')
        else:
            request.session['onboarding_step'] = current_step + 1
            return redirect('experiment:onboarding')

    # 4. Standard GET request output
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
def analytics_dashboard(request):
    """Admin dashboard displaying summary metrics and detailed trial & session records."""
    trials = ParticipantTrial.objects.select_related('session').all()

    # Summary metric calculations
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


# Alias to retain compatibility if referenced elsewhere in urls.py
admin_dashboard = analytics_dashboard


@staff_member_required
def download_trials_csv(request):
    """Exports all trial, session, manipulation check, survey, and demographic data to CSV."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="experiment_all_data.csv"'

    writer = csv.writer(response)

    # Expanded CSV Headers
    writer.writerow([
        # Session Metadata
        "Session ID",
        "Prolific PID",
        "Study ID",
        "Prolific Session ID",
        "Condition",
        "Total Score",
        "Total Help Sought",
        "Human Clicks",
        "AI Clicks",

        # Trial Details
        "Trial Number",
        "Difficulty",
        "Help Chosen",
        "Advisor Role",
        "Reaction Time (s)",
        "Is Correct",
        "Running Score",

        # Step 6: Manipulation & Attention Check Data
        "MC 1 (Respect)",
        "MC 2 (Control Others)",
        "MC 3 (Aggressive Tactics)",
        "MC 4 (High Esteem)",
        "MC 5 (Control vs Controlled)",
        "MC 6 (Way with Others)",
        "MC 7 (Talents Recognized)",
        "MC 8 (Seek Advice)",
        "Attention Check Value",
        "Passed Attention Check",

        # Post-Task Survey Ratings
        "Status Reduction",
        "Incompetent Rating",
        "Inexperienced Rating",
        "Lesser Rating",
        "Org Status Hurt Rating",
        "Held Against Rating",

        # Demographics
        "Participant Age",
        "Participant Gender",
    ])

    trials = ParticipantTrial.objects.select_related("session").all()

    for t in trials:
        s = t.session
        writer.writerow([
            # Session Metadata
            getattr(s, "session_id", "N/A") if s else "N/A",
            getattr(s, "prolific_pid", "N/A") if s else "N/A",
            getattr(s, "study_id", "N/A") if s else "N/A",
            getattr(s, "prolific_session_id", "N/A") if s else "N/A",
            getattr(s, "condition", "N/A") if s else "N/A",
            getattr(s, "total_score", 0) if s else 0,
            getattr(s, "total_help_sought", 0) if s else 0,
            getattr(s, "human_clicks", 0) if s else 0,
            getattr(s, "ai_clicks", 0) if s else 0,

            # Trial Details
            t.trial_number,
            t.difficulty,
            t.help_chosen,
            t.advisor_role,
            t.reaction_time,
            t.is_correct,
            t.running_score,

            # Step 6: Manipulation & Attention Check Data
            getattr(s, "mc_item_1_respect", "") if s else "",
            getattr(s, "mc_item_2_control_others", "") if s else "",
            getattr(s, "mc_item_3_aggressive_tactics", "") if s else "",
            getattr(s, "mc_item_4_high_esteem", "") if s else "",
            getattr(s, "mc_item_5_control_vs_controlled", "") if s else "",
            getattr(s, "mc_item_6_way_with_others", "") if s else "",
            getattr(s, "mc_item_7_talents_recognized", "") if s else "",
            getattr(s, "mc_item_8_seek_advice", "") if s else "",
            getattr(s, "mc_attention_check_value", "") if s else "",
            getattr(s, "passed_attention_check", False) if s else False,

            # Post-Task Survey Ratings
            getattr(s, "status_reduction", "") if s else "",
            getattr(s, "incompetent_rating", "") if s else "",
            getattr(s, "inexperienced_rating", "") if s else "",
            getattr(s, "lesser_rating", "") if s else "",
            getattr(s, "org_status_hurt_rating", "") if s else "",
            getattr(s, "held_against_rating", "") if s else "",

            # Demographics
            getattr(s, "participant_age", "") if s else "",
            getattr(s, "participant_gender", "") if s else "",
        ])

    return response

@staff_member_required
@require_POST
def clear_all_experiment_data(request):
    """Deletes all session and trial records without dropping schema or user accounts."""
    try:
        with transaction.atomic():
            # ParticipantTrial records will auto-delete via CASCADE if foreign key is set,
            # but deleting both explicitly guarantees clean resets across all DB engines.
            trial_count, _ = ParticipantTrial.objects.all().delete()
            session_count, _ = ChoiceExperimentSession.objects.all().delete()

        messages.success(
            request,
            f"Successfully cleared all data: {session_count} sessions and {trial_count} trials removed."
        )
    except Exception as e:
        messages.error(request, f"Failed to clear data: {str(e)}")

    return redirect('experiment:analytics_dashboard')
