"""
sentry.plugins.base.structs
~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010-2013 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""

from __future__ import absolute_import, print_function

__all__ = ['ReleaseHook']

from django.db import IntegrityError, transaction
from django.utils import timezone

from sentry.exceptions import HookValidationError
from sentry.models import Activity, Release


class ReleaseHook(object):
    def __init__(self, project):
        self.project = project

    def start_release(self, version, **values):
        if not Release.is_valid_version(version):
            raise HookValidationError('Invalid release version: %s' % version)

        try:
            with transaction.atomic():
                release, created = Release.objects.create(
                    version=version, organization_id=self.project.organization_id, **values
                ), True
        except IntegrityError:
            release, created = Release.objects.get(
                version=version,
                organization_id=self.project.organization_id,
            ), False
            release.update(**values)

        release.add_project(self.project, process_resolutions=not created)

    # TODO(dcramer): this is being used by the release details endpoint, but
    # it'd be ideal if most if not all of this logic lived there, and this
    # hook simply called out to the endpoint
    def set_commits(self, version, commit_list):
        """
        Commits should be ordered oldest to newest.

        Calling this method will remove all existing commit history.
        """
        if not Release.is_valid_version(version):
            raise HookValidationError('Invalid release version: %s' % version)

        project = self.project
        try:
            with transaction.atomic():
                release = Release.objects.create(
                    organization_id=project.organization_id, version=version
                )
        except IntegrityError:
            release = Release.objects.get(organization_id=project.organization_id, version=version)
        # Explicitly don't process resolutions here since we're setting a new
        # commit list, which will handle resolution processing.
        release.add_project(project, process_resolutions=False)

        release.set_commits(commit_list)

    def set_refs(self, release, **values):
        pass

    def finish_release(self, version, **values):
        if not Release.is_valid_version(version):
            raise HookValidationError('Invalid release version: %s' % version)

        values.setdefault('date_released', timezone.now())
        try:
            with transaction.atomic():
                release, created = Release.objects.create(
                    version=version,
                    organization_id=self.project.organization_id,
                    **values
                ), True
        except IntegrityError:
            release, created = Release.objects.get(
                version=version,
                organization_id=self.project.organization_id,
            ), False
            release.update(**values)

        release.add_project(self.project, process_resolutions=not created)

        Activity.objects.create(
            type=Activity.RELEASE,
            project=self.project,
            ident=Activity.get_version_ident(version),
            data={'version': version},
            datetime=values['date_released'],
        )
        self.set_refs(release=release, **values)

    def handle(self, request):
        raise NotImplementedError
