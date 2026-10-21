# Git identities and SSH

The global owner identity remains `maqsatto <m.syrtbay@outlook.com>`.
The second profile is `v2207function <kaiz.almaz.01@mail.ru>`.

Commit each completed responsibility separately with a specific message. The user explicitly assigned commits by the team's responsibility ownership. Use the ML owner for ML/data/evaluation and the application owner for API/mobile/infrastructure. This records task ownership; it is not evidence of unassisted manual authorship. SSH authentication
controls repository access; it does not set commit authorship.

Select an author for this repository only:

```bash
python scripts/git_identity.py owner
python scripts/git_identity.py friend
```

Return to `owner` before continuing the owner's work. The helper never changes
Git's global identity. To inspect the effective identity and its source:

```bash
git config --show-origin --get user.name
git config --show-origin --get user.email
```

The friend's separate SSH identity is configured outside the repository:

- Private key: `~/.ssh/id_ed25519_agrovision_v2207function`
- SSH host alias: `github-v2207function`
- SSH include: `~/.ssh/config.d/agrovision-v2207function.conf`
- Git profile template: `~/.config/git/profiles/v2207function.gitconfig`

The existing SSH configuration was preserved; a backup before adding the include
is at `~/.ssh/config.before-agrovision-v2207function`.
The public key was added to the verified GitHub account `v2207function` as
**AgroVision development**. Never commit the private key.

For a repository accessed using that account, the SSH URL format is:

```text
git@github-v2207function:OWNER/REPOSITORY.git
```

A remote repository is not created or configured by the profile helper.


Responsibility source supplied by the user: [team contribution document](https://docs.google.com/document/d/1C06l2fTc7dKkj14YN5zJjNv1504wT2kH/edit).

- ML/data/evaluation: v2207function (Матығұл Қайсар Алмасұлы).
- Backend/mobile/infrastructure: maqsatto (Сыртбай Мақсат Берікұлы).
- The older document names Flutter; current user instruction and Foundation choose React Native/Expo, which governs implementation. Historical accuracy claims in that document are not imported as measured results of this MVP.
