from . import gitlab
import logging as log
import json

GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


class Lgtms(gitlab.Resource):
    """Check that the right people reviewed it in the CE edition of gitlabs MergeRequest."""

    def refetch_info(self):
        gitlab_version = self._api.version()
        if gitlab_version.release >= (9, 2, 2):
            comment_url = '/projects/{0.project_id}/merge_requests/{0.iid}/notes'.format(self)
            get_award_url = '/projects/{0.project_id}/merge_requests/{0.iid}/award_emoji'.format(self)
            award_url = '/projects/{0.project_id}/merge_requests/{0.iid}/award_emoji?name=thumbsup'.format(self)
            glass_url = '/projects/{0.project_id}/merge_requests/{0.iid}/award_emoji?name=radioactive'.format(self)
        else:
            # GitLab botched the v4 api before 9.2.3
            comment_url = '/projects/{0.project_id}/merge_requests/{0.id}/notes'.format(self)
            get_award_url = '/projects/{0.project_id}/merge_requests/{0.id}/award_emoji'.format(self)
            award_url = '/projects/{0.project_id}/merge_requests/{0.id}/award_emoji?name=thumbsup'.format(self)
            glass_url = '/projects/{0.project_id}/merge_requests/{0.id}/award_emoji?name=radioactive'.format(self)


        """ Get list of people who are allowed to approve from master reviewers file """
        raw_url = '/projects/{0.project_id}/repository/files/lgtm.json/raw?ref=master'.format(self)
        lgtm_members = self._api.call(GET(raw_url))
        awards = self._api.call(GET(get_award_url))
        approvals_left = 2
        seen_self = False
        break_the_glass = False
        seen_broken_glass = False
        broken_by = False
        approved_by = []
        quick_check = []
        user_url = '/user'.format(self)
        me = self._api.call(GET(user_url))
        if 0 < len(awards):
            for i in range(len(awards)):
                if "radioactive" in awards[i]['name']:
                    break_the_glass = True
                    broken_by = awards[i]['user']['username']
                    approvals_left = 0
                    approved_by.append(awards[i])
                    if awards[i]['user']['id'] == me['id']:
                        seen_broken_glass = True

                if not break_the_glass:
                    if "thumbsup" in awards[i]['name']:
                        if awards[i]['user']['id'] == me['id']:
                            seen_self = True
                        if awards[i]['user']['username'] in lgtm_members:
                            if awards[i]['user']['username'] not in quick_check:
                                quick_check.append(awards[i]['user']['username'])
                                approvals_left = approvals_left - 1
                                approved_by.append(awards[i])

        if not seen_self:
            seen_self = True
            message = ' '
            for member in lgtm_members:
                message = ' @' + member + ' ' + message

            self._api.call(POST(comment_url, {'body': message + ' \n\nGot an emergency and need to force a merge ?\n\n break the glass by adding :radioactive: to the MR'}))
            self._api.call(POST(award_url))

        if break_the_glass:
            if not seen_broken_glass:
                message = ' '
                for member in lgtm_members:
                    message = ' @' + member + ' ' + message
                self._api.call(POST(comment_url, {'body': '@' + broken_by + ' has broken the glass, we will merge now! :radioactive: \n\n' + message}))
                self._api.call(POST(glass_url))


        self._info['approvals_left'] = approvals_left
        self._info['approved_by'] = approved_by

    @property
    def iid(self):
        return self.info['iid']

    @property
    def project_id(self):
        return self.info['project_id']

    @property
    def approvals_left(self):
        return self.info['approvals_left'] or 0

    @property
    def sufficient(self):
        return not self.info['approvals_left']

    @property
    def approver_usernames(self):
        return [who['user']['username'] for who in self.info['approved_by']]

    @property
    def approver_ids(self):
        """Return the uids of the approvers."""
        return [who['user']['id'] for who in self.info['approved_by']]

    def reapprove(self):
        """Impersonates the approvers and re-approves the merge_request as them.

        The idea is that we want to get the approvers, push the rebased branch
        (which may invalidate approvals, depending on GitLab settings) and then
        restore the approval status.
        """
        if self._api.version().release >= (9, 2, 2):
            approve_url = '/projects/{0.project_id}/merge_requests/{0.iid}/approve'.format(self)
        else:
            # GitLab botched the v4 api before 9.2.3
            approve_url = '/projects/{0.project_id}/merge_requests/{0.id}/approve'.format(self)

        for uid in self.approver_ids:
            self._api.call(POST(approve_url), sudo=uid)
