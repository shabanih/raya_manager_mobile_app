from django.db import models
from user_app.models import User, Unit, MyHouse, Renter


class Poll(models.Model):

    PARTICIPANT_TYPE = (
        ('all', 'همه'),
        ('owners', 'فقط مالکین'),
        ('renters', 'فقط مستاجرین'),
    )

    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name="polls"
    )

    title = models.CharField(
        max_length=255
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )

    start_date = models.DateTimeField()

    end_date = models.DateTimeField()

    # -----------------------------------------
    # افراد مجاز به شرکت
    # -----------------------------------------
    participant_type = models.CharField(
        max_length=10,
        choices=PARTICIPANT_TYPE,
        default='all'
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.title

    @property
    def active_owner_count(self):
        return self.house.units.filter(
            is_active=True
        ).count()

    @property
    def active_renter_count(self):
        return Renter.objects.filter(
            unit__myhouse=self.house,
            unit__is_active=True,
            renter_is_active=True
        ).count()

    @property
    def eligible_participant_count(self):

        if self.participant_type == 'owners':
            return self.active_owner_count

        if self.participant_type == 'renters':
            return self.active_renter_count

        return (
                self.active_owner_count +
                self.active_renter_count
        )


class Question(models.Model):
    QUESTION_TYPE = (
        ('yesno', 'بلی / خیر'),
        ('single', 'چند گزینه‌ای (یک انتخاب)'),
        ('multi', 'چند انتخابی'),
    )

    poll = models.ForeignKey(
        Poll,
        on_delete=models.CASCADE,
        related_name="questions"
    )

    title = models.CharField(max_length=500)
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPE)

    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.title


class Choice(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="choices"
    )

    title = models.CharField(max_length=255)

    def __str__(self):
        return self.title

    def vote_count(self):
        return self.vote_set.count()

    def percentage(self):
        total = Vote.objects.filter(question=self.question).values('user').distinct().count()
        if total == 0:
            return 0
        return round((self.vote_count() / total) * 100, 1)


class Vote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="votes"
    )
    choice = models.ForeignKey(Choice, on_delete=models.CASCADE)

    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'user', 'choice'],
                name='unique_vote_per_choice'
            )
        ]
