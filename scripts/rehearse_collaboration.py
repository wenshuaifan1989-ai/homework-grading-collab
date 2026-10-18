"""Single-operator Git rehearsal on temporary local repositories. No GitHub calls."""
import json
from pathlib import Path
import subprocess
import tempfile


def git(directory, *args, ok=True):
    result = subprocess.run(['git', '-C', str(directory), '-c', 'user.name=Local Rehearsal',
        '-c', 'user.email=rehearsal@example.invalid', *args], capture_output=True, text=True,
        encoding='utf-8', errors='replace')
    if ok and result.returncode:
        raise RuntimeError('Local rehearsal command failed: '+args[0])
    return result


def commit(directory, contents, message):
    (directory/'drill.txt').write_text(contents, encoding='utf-8')
    git(directory, 'add', '--', 'drill.txt')
    git(directory, 'commit', '-m', message)
    return git(directory, 'rev-parse', 'HEAD').stdout.strip()


def rehearse():
    with tempfile.TemporaryDirectory(prefix='git-collab-rehearsal-') as temporary:
        root = Path(temporary)
        remote, first, second = root/'remote.git', root/'first', root/'second'
        git(root, 'init', '--bare', '--initial-branch=develop', str(remote))
        git(root, 'clone', str(remote), str(first))
        commit(first, 'shared line\n', 'Initialize harmless drill file')
        git(first, 'push', 'origin', 'develop')
        git(root, 'clone', str(remote), str(second))
        initial_equal = git(first, 'rev-parse', 'HEAD').stdout == git(second, 'rev-parse', 'HEAD').stdout
        git(second, 'switch', '-c', 'feature/second')
        commit(second, 'second contribution\n', 'Second simulated contribution')
        git(first, 'switch', '-c', 'feature/first')
        commit(first, 'first contribution\n', 'First simulated contribution')
        git(first, 'push', 'origin', 'HEAD:develop')  # temporary local bare repository only
        git(second, 'fetch', 'origin')
        conflict = git(second, 'merge', 'origin/develop', ok=False)
        conflict_detected = conflict.returncode != 0 and 'UU drill.txt' in git(second, 'status', '--porcelain').stdout
        if not conflict_detected: raise RuntimeError('Expected local conflict was not detected')
        resolved_sha = commit(second, 'first contribution\nsecond contribution\n', 'Resolve and preserve both contributions')
        git(second, 'push', 'origin', 'HEAD:develop')
        git(first, 'switch', 'develop')
        git(first, 'pull', '--ff-only', 'origin', 'develop')
        sync_after_conflict = git(first, 'rev-parse', 'HEAD').stdout.strip() == resolved_sha
        drill_sha = commit(first, 'first contribution\nsecond contribution\ndrill enabled\n', 'Reversible drill only')
        git(first, 'push', 'origin', 'develop')
        git(second, 'switch', 'develop')
        git(second, 'pull', '--ff-only', 'origin', 'develop')
        git(second, 'revert', '--no-edit', drill_sha)
        revert_sha = git(second, 'rev-parse', 'HEAD').stdout.strip()
        git(second, 'push', 'origin', 'develop')
        git(first, 'pull', '--ff-only', 'origin', 'develop')
        content = (first/'drill.txt').read_text(encoding='utf-8')
        result = {'mode': 'SINGLE_OPERATOR_LOCAL_REHEARSAL', 'two_people_verified': False,
            'github_protection_tested': False, 'external_pushes': 0, 'initial_clone_sha_equal': initial_equal,
            'conflict_detected': conflict_detected, 'resolved_sha_equal': sync_after_conflict,
            'revert_preserves_both_contributions': content == 'first contribution\nsecond contribution\n',
            'final_ff_only_sha_equal': git(first, 'rev-parse', 'HEAD').stdout.strip() == revert_sha,
            'revert_commit': revert_sha}
        if not all(result[k] for k in ('initial_clone_sha_equal', 'conflict_detected', 'resolved_sha_equal',
                   'revert_preserves_both_contributions', 'final_ff_only_sha_equal')):
            raise RuntimeError('Local rehearsal did not satisfy its assertions')
        return result


if __name__ == '__main__':
    print(json.dumps(rehearse(), sort_keys=True))
