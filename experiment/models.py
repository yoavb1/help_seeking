import uuid
from django.db import models


class ChoiceExperimentSession(models.Model):
    # Prolific Identifiers
    prolific_pid = models.CharField(max_length=200, blank=True, null=True)
    study_id = models.CharField(max_length=200, blank=True, null=True)
    prolific_session_id = models.CharField(max_length=200, blank=True, null=True)
    session_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)

    # Experimental Group Manipulation
    condition = models.CharField(max_length=20, choices=[('prestige', 'Prestige'), ('dominance', 'Dominance')])
    created_at = models.DateTimeField(auto_now_add=True)

    # Core App Aggregated Task Metrics
    total_score = models.IntegerField(default=0)
    total_help_sought = models.IntegerField(default=0)
    human_clicks = models.IntegerField(default=0)
    ai_clicks = models.IntegerField(default=0)

    # --- Step 6: Manipulation Check Items (1-7 Scale) ---
    mc_item_1_respect = models.IntegerField(null=True, blank=True)
    mc_item_2_control_others = models.IntegerField(null=True, blank=True)
    mc_item_3_aggressive_tactics = models.IntegerField(null=True, blank=True)
    mc_item_4_high_esteem = models.IntegerField(null=True, blank=True)
    mc_item_5_control_vs_controlled = models.IntegerField(null=True, blank=True)
    mc_item_6_way_with_others = models.IntegerField(null=True, blank=True)
    mc_item_7_talents_recognized = models.IntegerField(null=True, blank=True)
    mc_item_8_seek_advice = models.IntegerField(null=True, blank=True)

    # --- Step 6: Attention Check ---
    mc_attention_check_value = models.IntegerField(null=True, blank=True)
    passed_attention_check = models.BooleanField(default=False)

    # Post-Experiment Demographics
    participant_age = models.IntegerField(null=True, blank=True)
    participant_gender = models.CharField(max_length=30, null=True, blank=True)

    class Meta:
        db_table = 'choice_experiment_session'

    def __str__(self):
        return f"Session {self.session_id} - {self.condition}"


class ParticipantTrial(models.Model):
    session = models.ForeignKey(ChoiceExperimentSession, on_delete=models.CASCADE, related_name='trials')
    trial_number = models.IntegerField()

    # Updated choices supporting Easy, Medium, and Hard
    DIFFICULTY_CHOICES = [
        ('E', 'Easy'),
        ('M', 'Medium'),
        ('H', 'Hard'),
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)

    help_chosen = models.CharField(max_length=10, choices=[('none', 'None'), ('human', 'Human'), ('ai', 'AI')])

    reaction_time = models.FloatField()
    is_correct = models.BooleanField(default=False)
    running_score = models.IntegerField(default=0)

    class Meta:
        db_table = 'participant_trial'

    def __str__(self):
        return f"Session {self.session.session_id} | Trial {self.trial_number} | Score: {self.running_score}"


class SurveyResponse(models.Model):
    # Optional: Associate with a user or session
    # user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # 1. Task Experience
    nervous_seeking = models.IntegerField()
    task_anxiety = models.IntegerField()
    task_difficulty = models.IntegerField()

    # 2. Social Costs & Status Concerns
    status_reduction = models.IntegerField()
    incompetent = models.IntegerField()
    inexperienced = models.IntegerField()
    lesser = models.IntegerField()
    org_status_hurt = models.IntegerField()
    held_against = models.IntegerField()

    # 3. Expectations of Assistance Compliance
    subordinate_rejection_concern = models.IntegerField()
    subordinate_compliance_expectation = models.IntegerField()

    # 4. Relational & Interpersonal Impact
    relational_strengthen = models.IntegerField()
    relational_trust = models.IntegerField()
    relational_collaboration = models.IntegerField()
    relational_value_subordinate = models.IntegerField()

    # 5. Advisor Utility & Perceived Competence
    instrumental_human = models.IntegerField()
    instrumental_ai = models.IntegerField()
    perceived_competence_human = models.IntegerField()
    perceived_competence_ai = models.IntegerField()

    def __str__(self):
        return f"Survey Response {self.id} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"