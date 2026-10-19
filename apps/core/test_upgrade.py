import datetime as dt
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.habits.models import Habit
from apps.habits.services import sync_habits_for_date
from apps.tasks.models import Tag, Task
from apps.assistant.models import AssistantDraft


class WebUpgradeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('upgrade-user', password='StrongTest_41Pass')
        self.client.force_login(self.user)

    def test_recurrence_preserves_priority_and_tags(self):
        label = Tag.objects.create(user=self.user, name='learning')
        habit = Habit.objects.create(user=self.user, title='Study', priority='high')
        habit.tags.add(label)
        tomorrow = timezone.localdate() + dt.timedelta(days=1)
        tasks = sync_habits_for_date(self.user, tomorrow)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].priority, 'high')
        self.assertEqual(list(tasks[0].tags.all()), [label])
        self.assertEqual(sync_habits_for_date(self.user, tomorrow), [])

    def test_far_habit_reads_do_not_generate_rows(self):
        Habit.objects.create(user=self.user, title='Reading')
        sync_habits_for_date(self.user, timezone.localdate() + dt.timedelta(days=2000))
        self.assertEqual(Task.objects.count(), 0)

    def test_habit_end_without_start_is_invalid(self):
        habit = Habit(user=self.user, title='Invalid', end_time=dt.time(12))
        with self.assertRaises(ValidationError):
            habit.full_clean()

    def test_profile_is_owned_and_export_is_versioned(self):
        response = self.client.post(reverse('accounts:profile'), {'first_name':'Sara','last_name':'','email':'sara@example.com'})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name,'Sara')
        response = self.client.get(reverse('accounts:export'))
        self.assertEqual(response.json()['schema_version'],'2.0')
        self.assertIn('focus_sessions',response.json())
        self.assertIn('assistant_messages',response.json())
        self.assertIn('no-store',response['Cache-Control'])
        self.assertNotIn('token',response.json())

    def test_acceptance_does_not_recreate_deleted_task(self):
        draft = AssistantDraft.objects.create(user=self.user, payload={}, accepted_at=timezone.now())
        response = self.client.post(reverse('assistant:accept'), {'draft_id':str(draft.token)})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['already_accepted'])
        self.assertEqual(Task.objects.count(),0)

    @override_settings(PUBLIC_ORIGIN='')
    def test_no_internal_host_is_emitted_as_canonical(self):
        self.client.logout()
        response=self.client.get('/')
        self.assertNotContains(response,'http://testserver')
        self.assertNotContains(response,'rel="canonical"')
        self.assertContains(response,'application/ld+json')

    def test_sensitive_pages_require_login(self):
        self.client.logout()
        for name in ('tasks:smart_add','tasks:board','assistant:index','calendar_view:subscription'):
            response=self.client.get(reverse(name))
            self.assertEqual(response.status_code,302)

    def test_recurrence_starts_on_chosen_date(self):
        today=timezone.localdate()
        habit=Habit.objects.create(user=self.user,title='Starts later',starts_on=today+dt.timedelta(days=2))
        self.assertEqual(sync_habits_for_date(self.user,today),[])
        self.assertEqual(len(sync_habits_for_date(self.user,habit.starts_on)),1)

    def test_edit_habit_updates_future_but_preserves_history(self):
        from apps.habits.services import reconcile_future_occurrences
        today=timezone.localdate()
        habit=Habit.objects.create(user=self.user,title='Old title')
        yesterday=Task.objects.create(user=self.user,habit=habit,title='History',date=today-dt.timedelta(days=1),status='done')
        future=Task.objects.create(user=self.user,habit=habit,title='Old title',date=today+dt.timedelta(days=1))
        habit.title='New title';habit.save()
        reconcile_future_occurrences(habit)
        yesterday.refresh_from_db();future.refresh_from_db()
        self.assertEqual(yesterday.title,'History')
        self.assertEqual(future.title,'New title')
        habit.active=False;habit.save()
        reconcile_future_occurrences(habit)
        self.assertFalse(Task.objects.filter(pk=future.pk).exists())
        self.assertTrue(Task.objects.filter(pk=yesterday.pk).exists())

    @override_settings(PASSWORD_RESET_ENABLED=False)
    def test_password_reset_does_not_pretend_delivery_without_smtp(self):
        from unittest.mock import patch
        self.client.logout()
        with patch('django.core.mail.EmailMultiAlternatives.send') as send:
            response=self.client.post(reverse('accounts:password_reset'),{'email':'sara@example.com'})
            self.assertEqual(response.status_code,503)
            send.assert_not_called()

    def test_signed_preview_requires_ambiguous_confirmation(self):
        url=reverse('tasks:smart_add')
        phrase='مطالعه دوشنبه'
        preview=self.client.post(url,{'intent':'preview','phrase':phrase})
        self.assertTrue(preview.context['parsed'].warnings)
        data={'intent':'save','phrase':phrase,'preview_token':preview.context['preview_token'],'title':'Study','date':timezone.localdate().isoformat(),'priority':'medium','recurrence':'none','parser_warnings':''}
        denied=self.client.post(url,data)
        self.assertEqual(denied.status_code,422)
        self.assertEqual(Task.objects.count(),0)
        data['confirm_ambiguous']='1'
        self.assertEqual(self.client.post(url,data).status_code,302)

    def test_missing_preview_signature_is_rejected(self):
        response=self.client.post(reverse('tasks:smart_add'),{'intent':'save','title':'Bypass','date':timezone.localdate().isoformat(),'priority':'medium','recurrence':'none'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(Task.objects.count(),0)

    def test_duplicate_keeps_private_labels_and_resets_subtasks(self):
        from apps.tasks.models import SubTask
        task=Task.objects.create(user=self.user,title='Copy',date=timezone.localdate())
        label=Tag.objects.create(user=self.user,name='work');task.tags.add(label)
        SubTask.objects.create(user=self.user,task=task,title='A step',is_completed=True)
        response=self.client.post(reverse('tasks:duplicate',args=[task.pk]))
        self.assertEqual(response.status_code,200)
        copy=Task.objects.exclude(pk=task.pk).get()
        self.assertEqual(list(copy.tags.all()),[label])
        self.assertFalse(copy.subtasks.get().is_completed)

    @override_settings(FRAME_ANCESTORS=["'self'", "https://manus.im"], MANAGED_HOSTING=True)
    def test_frame_ancestors_are_restricted(self):
        response=self.client.get('/')
        policy=response['Content-Security-Policy']
        self.assertIn('frame-ancestors',policy)
        self.assertIn('https://manus.im',policy)
        self.assertNotIn('frame-ancestors *',policy)
