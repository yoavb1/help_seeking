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
from .models import *
from django.views.decorators.cache import never_cache
import traceback
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Read the completion code from the environment variable
PROLIFIC_COMPLETION_CODE = os.getenv('PROLIFIC_COMPLETION_CODE')

def load_and_shuffle_questions(count, filename='questions.json', difficulty=None):
    """
    Utility to load questions from JSON, separate by difficulty (M then H),
    shuffle each difficulty group independently, and reassign sequence numbers.
    """
    json_path = os.path.join(
        settings.BASE_DIR, 'experiment', 'data', filename
    )

    if not os.path.exists(json_path):
        return []

    with open(json_path, 'r', encoding='utf-8') as f:
        all_questions = json.load(f)

    # If a specific single difficulty filter was requested, maintain existing behavior
    if difficulty:
        diff_map = {'easy': 'E', 'medium': 'M', 'hard': 'H', 'E': 'E', 'M': 'M', 'H': 'H'}
        target_diff = diff_map.get(str(difficulty).lower(), str(difficulty).upper())
        filtered_questions = [
            q for q in all_questions if q.get('difficulty') == target_diff
        ]
        if not filtered_questions:
            return []

        random.shuffle(filtered_questions)
        ordered_pool = filtered_questions

    else:
        # Separate questions into Medium and Hard pools
        medium_questions = [q for q in all_questions if q.get('difficulty') == 'M']
        hard_questions = [q for q in all_questions if q.get('difficulty') == 'H']
        other_questions = [q for q in all_questions if q.get('difficulty') not in ['M', 'H']]

        # Shuffle each difficulty group independently
        random.shuffle(medium_questions)
        random.shuffle(hard_questions)
        random.shuffle(other_questions)

        # Combine so ALL Medium come first, then ALL Hard, followed by any others
        ordered_pool = medium_questions + hard_questions + other_questions

    if not ordered_pool:
        return []

    # Select requested count and assign sequential trial numbers 1..N
    selected_questions = []
    for i in range(count):
        q = dict(ordered_pool[i % len(ordered_pool)])
        q['number'] = i + 1  # Assign trial number 1..N
        selected_questions.append(q)

    return selected_questions


@never_cache
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
        request.session['show_ai_first'] = random.choice([True, False])
        if assigned_condition == 'dominance':
            style = 'Leads with dominant and assertiveness. Controlling and forceful towards others.'
        else:
            style = 'Leads with respect and admiration. Sharing information and skills with others.'

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

        # STEP 1: Combined Welcome & Consent -> Jump straight to Step 3
        if current_step == 1:
            request.session['onboarding_step'] = 3
            return redirect('experiment:onboarding')

        elif current_step == 6:
            user_answer = request.POST.get('comprehension_check')

            # Correct options: 1 = Dominance, 2 = Prestige, 3 = Control
            expected_answers = {
                'dominance': '1',
                'prestige': '2',
                'control': '3'
            }
            correct_answer = expected_answers.get(experiment_session.condition, '1')

            if user_answer and user_answer == correct_answer:
                if hasattr(experiment_session, 'passed_comprehension_check'):
                    experiment_session.passed_comprehension_check = True
                    experiment_session.save()

                request.session['onboarding_step'] = 7
                return redirect('experiment:onboarding')
            else:
                # If server-side validation fails, return step 6 with error
                return render(
                    request,
                    'experiment/onboarding.html',
                    {
                        'step': 6,
                        'condition': experiment_session.condition,
                        'error_message': 'Incorrect answer. Please re-read the description above and select the correct option to continue.'
                    }
                )

        if current_step == 7:
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

            # Advance to Step 7 (Overview & Task Rules)
            request.session['onboarding_step'] = 8
            return redirect('experiment:onboarding')

        # STEP 8: Final Onboarding Step (Task Overview) -> Redirect to Practice Run
        elif current_step == 8:
            # Clear or complete onboarding session step if needed, then finish onboarding
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


@never_cache
def practice_run_view(request):
    """Loads the dashboard layout configured as an unlogged practice run with dynamic questions."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    max_trials = getattr(settings, 'EXPERIMENT_PRACTICE_TRIALS', 5)
    questions = load_and_shuffle_questions(count=max_trials, filename='questions_practice.json')

    context = {
        'show_ai_first': request.session['show_ai_first'],
        'session': session,
        'style': request.session['style'],
        'is_practice': True,
        'max_trials': max_trials,
        'questions_json': json.dumps(questions),  # Passed as JSON string
    }

    return render(request, 'experiment/dashboard.html', context)


@never_cache
def ready_alert_view(request):
    """Intermediate warning screen confirming that practice is over."""
    return redirect('experiment:dashboard')
    if request.method == "POST":
        return redirect('experiment:dashboard')
    return render(request, 'experiment/ready_alert.html')


@never_cache
def dashboard_view(request):
    """Loads the dashboard layout configured as the live experiment with dynamic questions."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    max_trials = getattr(settings, 'EXPERIMENT_LIVE_TRIALS', 50)
    questions = load_and_shuffle_questions(count=max_trials, filename='questions_live.json')

    context = {
        'show_ai_first': request.session['show_ai_first'],
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
            is_practice = t.get("is_practice", False)
            trial_num = t.get("trial_number")
            trial_id = t.get("trial_id")

            # 1. Save THIS trial immediately to the DB
            trial, created = ParticipantTrial.objects.update_or_create(
                session=session,
                trial_number=trial_num,
                is_practice=is_practice,  # Differentiates Practice #1 from Live #1
                defaults={
                    "trial_id": trial_id,
                    "difficulty": diff_code,
                    "help_chosen": help_choice,
                    "reaction_time": t.get("reaction_time", 0.0),
                    "is_correct": is_correct,
                    "running_score": t.get("running_score", 0),
                }
            )

            # Award +3 for correct answer
            if is_correct:
                session.total_score += 3

            # Subtract 1 point surcharge for seeking help (Human or AI)
            if help_choice != "none":
                session.total_score -= 1
                session.total_help_sought = (session.total_help_sought or 0) + 1

            if help_choice == "human":
                session.human_clicks = (session.human_clicks or 0) + 1
            elif help_choice == "ai":
                session.ai_clicks = (session.ai_clicks or 0) + 1

            session.save()

            return JsonResponse({"status": "success", "message": "Trial logged"})

        except Exception as e:
            traceback.print_exc()
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

                # Normalize difficulty code safely
                raw_diff = str(t.get('difficulty', 'E')).upper()
                diff_code = diff_map.get(raw_diff, 'E')

                # Tally metrics with updated scoring
                if is_correct:
                    total_score += 3
                if help_choice != 'none':
                    total_score -= 1  # 1 point deduction for seeking help
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


@never_cache
def survey_view(request):
    """Handles capturing evaluation metrics and creating a SurveyResponse record."""
    session_id = request.session.get('experiment_sid')
    session = get_object_or_404(
        ChoiceExperimentSession, session_id=session_id
    )

    if request.method == "POST":
        # 1. Save directly to ChoiceExperimentSession (for trial-by-trial CSV export)
        session.status_reduction = request.POST.get('status_reduction')
        session.incompetent_rating = request.POST.get('incompetent')
        session.inexperienced_rating = request.POST.get('inexperienced')
        session.lesser_rating = request.POST.get('lesser')
        session.org_status_hurt_rating = request.POST.get('org_status_hurt')
        session.held_against_rating = request.POST.get('held_against')
        session.save()

        # 2. ALSO save to SurveyResponse model (for standalone Survey Dashboard tab & CSV)
        SurveyResponse.objects.create(
            # Section 1
            nervous_seeking=request.POST.get('nervous_seeking'),
            task_anxiety=request.POST.get('task_anxiety'),
            task_difficulty=request.POST.get('task_difficulty'),
            agree_with_manipulation=request.POST.get('agree_with_manipulation'),

            # Section 2
            status_reduction=request.POST.get('status_reduction'),
            incompetent=request.POST.get('incompetent'),
            inexperienced=request.POST.get('inexperienced'),
            lesser=request.POST.get('lesser'),
            org_status_hurt=request.POST.get('org_status_hurt'),
            held_against=request.POST.get('held_against'),

            # Section 3
            subordinate_rejection_concern=request.POST.get('subordinate_rejection_concern'),
            subordinate_compliance_expectation=request.POST.get('subordinate_compliance_expectation'),

            # Section 4
            relational_strengthen=request.POST.get('relational_strengthen'),
            relational_trust=request.POST.get('relational_trust'),
            relational_collaboration=request.POST.get('relational_collaboration'),
            relational_value_subordinate=request.POST.get('relational_value_subordinate'),

            # Section 5
            instrumental_human=request.POST.get('instrumental_human'),
            instrumental_ai=request.POST.get('instrumental_ai'),
            perceived_competence_human=request.POST.get('perceived_competence_human'),
            perceived_competence_ai=request.POST.get('perceived_competence_ai')
        )

        return redirect('experiment:task_update_notice')
    if 'dominant' in request.session['style']:
        style = "leading with dominant and assertiveness and being controlling and forceful towards others"
    else:
        style = "leading with respect and admiration, while sharing information and skills with others"

    return render(request, 'experiment/survey.html', context={'style': style})


@never_cache
def task_update_notice(request):
    """
    Dedicated transition screen informing participants
    that Task 2 is skipped due to time constraints.
    """

    return render(request, 'experiment/task_update.html')


@never_cache
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


@never_cache
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
    """Admin dashboard displaying summary metrics, trial records, and workspace survey responses."""
    trials = ParticipantTrial.objects.select_related('session').all()

    # Fetch all workspace survey responses for the new dashboard tab
    survey_responses = SurveyResponse.objects.all().order_by('-created_at')

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
        'survey_responses': survey_responses,
        'total_responses': survey_responses.count(),
        'accuracy_rate': accuracy_rate,
        'avg_rt': avg_rt,
        'ai_usage_rate': ai_usage_rate,
    }
    return render(request, 'admin_dashboard.html', context)


@staff_member_required
def download_trials_csv(request):
    """Exports all trial, session, manipulation check, full workspace survey, and demographic data to CSV."""
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
        "Trial ID",
        "Is Practice",
        "Difficulty",
        "Help Chosen",
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

        # # Post-Task Workspace Survey (Section 1 to Section 5)
        # "Nervous Seeking",
        # "Task Anxiety",
        # "Task Difficulty",
        # "Status Reduction",
        # "Incompetent Rating",
        # "Inexperienced Rating",
        # "Lesser Rating",
        # "Org Status Hurt Rating",
        # "Held Against Rating",
        # "Subordinate Rejection Concern",
        # "Subordinate Compliance Expectation",
        # "Relational Strengthen",
        # "Relational Trust",
        # "Relational Collaboration",
        # "Relational Value Subordinate",
        # "Instrumental Human",
        # "Instrumental AI",
        # "Perceived Competence Human",
        # "Perceived Competence AI",

        # Demographics
        "Participant Age",
        "Participant Gender",
    ])

    trials = ParticipantTrial.objects.select_related("session").all()

    for t in trials:
        s = t.session
        # survey = getattr(s, 'survey_response', None) if s else None

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
            getattr(t, "trial_id", "N/A") or "N/A", # 👈 ADDED HERE
            t.is_practice,                         # 👈 ADDED HERE
            t.difficulty,
            t.help_chosen,
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

            # Post-Task Workspace Survey Data
            # getattr(survey, "nervous_seeking", getattr(s, "nervous_seeking", "")),
            # getattr(survey, "task_anxiety", getattr(s, "task_anxiety", "")),
            # getattr(survey, "task_difficulty", getattr(s, "task_difficulty", "")),
            # getattr(survey, "status_reduction", getattr(s, "status_reduction", "")),
            # getattr(survey, "incompetent", getattr(s, "incompetent_rating", "")),
            # getattr(survey, "inexperienced", getattr(s, "inexperienced_rating", "")),
            # getattr(survey, "lesser", getattr(s, "lesser_rating", "")),
            # getattr(survey, "org_status_hurt", getattr(s, "org_status_hurt_rating", "")),
            # getattr(survey, "held_against", getattr(s, "held_against_rating", "")),
            # getattr(survey, "subordinate_rejection_concern", ""),
            # getattr(survey, "subordinate_compliance_expectation", ""),
            # getattr(survey, "relational_strengthen", ""),
            # getattr(survey, "relational_trust", ""),
            # getattr(survey, "relational_collaboration", ""),
            # getattr(survey, "relational_value_subordinate", ""),
            # getattr(survey, "instrumental_human", ""),
            # getattr(survey, "instrumental_ai", ""),
            # getattr(survey, "perceived_competence_human", ""),
            # getattr(survey, "perceived_competence_ai", ""),

            # Demographics
            getattr(s, "participant_age", "") if s else "",
            getattr(s, "participant_gender", "") if s else "",
        ])

    return response

@staff_member_required
def download_survey_csv(request):
    """Exports standalone workspace survey data to CSV."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="workspace_survey_responses.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "ID", "Session ID",
        "Prolific PID",
        "Submitted At",
        "Nervous Seeking", "Task Anxiety", "Task Difficulty", 'Agree with Manipulation',
        "Status Reduction", "Incompetent", "Inexperienced", "Lesser", "Org Status Hurt", "Held Against",
        "Subordinate Rejection Concern", "Subordinate Compliance Expectation",
        "Relational Strengthen", "Relational Trust", "Relational Collaboration", "Relational Value Subordinate",
        "Instrumental Human", "Instrumental AI", "Perceived Competence Human", "Perceived Competence AI"
    ])

    for r in SurveyResponse.objects.all().order_by('-created_at'):
        session = getattr(r, 'session', None)

        session_id = getattr(session, 'session_id', 'N/A') if session else getattr(r, 'session_id', 'N/A')
        prolific_pid = getattr(session, 'prolific_pid', 'N/A') if session else getattr(r, 'prolific_pid', 'N/A')

        writer.writerow([
            r.id, session_id, prolific_pid,
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(r, 'created_at') else "",
            r.nervous_seeking, r.task_anxiety, r.task_difficulty, r.agree_with_manipulation,
            r.status_reduction, r.incompetent, r.inexperienced, r.lesser, r.org_status_hurt, r.held_against,
            r.subordinate_rejection_concern, r.subordinate_compliance_expectation,
            r.relational_strengthen, r.relational_trust, r.relational_collaboration, r.relational_value_subordinate,
            r.instrumental_human, r.instrumental_ai, r.perceived_competence_human, r.perceived_competence_ai
        ])

    return response


@staff_member_required
@require_POST
def clear_all_experiment_data(request):
    """Deletes all session, trial, and survey records without dropping schema or user accounts."""
    try:
        with transaction.atomic():
            trial_count, _ = ParticipantTrial.objects.all().delete()
            session_count, _ = ChoiceExperimentSession.objects.all().delete()
            survey_count, _ = SurveyResponse.objects.all().delete()

        messages.success(
            request,
            f"Successfully cleared all data: {session_count} sessions, {trial_count} trials, and {survey_count} survey responses removed."
        )
    except Exception as e:
        messages.error(request, f"Failed to clear data: {str(e)}")

    return redirect(
        'experiment:analytics_dashboard')
