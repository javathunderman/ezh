

make changes to submodule (gem5 or dramsim) (dramsim as example)

cd to submodule: `cd DRAMsim3`

Stage changes: `git add .`

Commit changes: `git commit -m "Commit message"`

Push to remote: `git push`

cd to root: `cd ..`

Stage changes in root repo: `git add .`

Commit changes to root repo: `git commit -m "Root commit message"`

Push to remote root: `git push`



If you fall off a branch: `git checkout master`
If you need to undo a commit + unstage:  `git reset HEAD~1`
                       " + not unstage:  `git reset --soft HEAD~1`