from django.db import models
import uuid


class ChoiceExperimentSession(models.Model):
    session_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)

    # Experimental Group Manipulation
    condition = models.CharField(max_length=20, choices=[('prestige', 'Prestige'), ('dominance', 'Dominance')])
    created_at = models.DateTimeField(auto_now_add=True)

    # Core App Aggregated Task Metrics
    total_score = models.IntegerField(default=0)
    total_help_sought = models.IntegerField(default=0)
    human_clicks = models.IntegerField(default=0)
    ai_clicks = models.IntegerField(default=0)

    # Post-Experiment Mediation Metrics
    image_cost_rating = models.IntegerField(null=True, blank=True)
    closeness_rating = models.IntegerField(null=True, blank=True)

    # Post-Experiment Demographics
    participant_age = models.IntegerField(null=True, blank=True)
    participant_gender = models.CharField(max_length=30, null=True, blank=True)

    def __str__(self):
        return f"Session {self.session_id} - {self.condition}"


class ParticipantTrial(models.Model):
    session = models.ForeignKey(ChoiceExperimentSession, on_delete=models.CASCADE, related_name='trials')
    trial_number = models.IntegerField()
    difficulty = models.CharField(max_length=10, choices=[('easy', 'Easy'), ('hard', 'Hard')])

    # Core system choice type tracking
    help_chosen = models.CharField(max_length=10, choices=[('none', 'None'), ('human', 'Human'), ('ai', 'AI')])

    # 🌟 NEW FIELD: Logs whether the selected advice came from a Manager, Peer, or Subordinate
    advisor_role = models.CharField(max_length=20, default='none', choices=[
        ('none', 'None'),
        ('manager', 'Manager'),
        ('peer', 'Peer'),
        ('subordinate', 'Subordinate')
    ])

    reaction_time = models.FloatField()
    is_correct = models.BooleanField(default=False)
    running_score = models.IntegerField(default=0)

    def __str__(self):
        return f"Session {self.session.session_id} | Trial {self.trial_number} | Score: {self.running_score}"