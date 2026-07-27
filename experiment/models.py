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

    # Post-Experiment Mediation Metrics (Help-Seeking / Image Cost Scale)
    status_reduction = models.IntegerField(null=True, blank=True)
    incompetent_rating = models.IntegerField(null=True, blank=True)
    inexperienced_rating = models.IntegerField(null=True, blank=True)
    lesser_rating = models.IntegerField(null=True, blank=True)
    org_status_hurt_rating = models.IntegerField(null=True, blank=True)
    held_against_rating = models.IntegerField(null=True, blank=True)

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

    advisor_role = models.CharField(
        max_length=20,
        default='none',
        choices=[
            ('none', 'None'),
            ('manager', 'Manager'),
            ('peer', 'Peer'),
            ('subordinate', 'Subordinate'),
        ],
    )

    reaction_time = models.FloatField()
    is_correct = models.BooleanField(default=False)
    running_score = models.IntegerField(default=0)

    class Meta:
        db_table = 'participant_trial'

    def __str__(self):
        return f"Session {self.session.session_id} | Trial {self.trial_number} | Score: {self.running_score}"