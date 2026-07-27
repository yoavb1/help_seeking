from django.core.management.base import BaseCommand
import django
import os
import sys

# Replace 'myproject.settings' with your actual settings path (e.g., 'config.settings')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "HelpSeeking.settings")

# Add project root directory to Python path if needed
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

django.setup()

from experiment.models import *

class Command(BaseCommand):
    help = "Deletes all experiment participant data while keeping superusers."

    def handle(self, *args, **options):
        trial_count, _ = ParticipantTrial.objects.all().delete()
        session_count, _ = ChoiceExperimentSession.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {trial_count} trials and {session_count} sessions!"
            )
        )