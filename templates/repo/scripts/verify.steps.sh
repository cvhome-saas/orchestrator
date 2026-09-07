# The gates CI runs, in order. `step "<name>" <command...>` stops at the first failure.
# Replace these with the repo's real gates; keep them identical to the CI workflow.
step "diff is clean of whitespace errors"  git diff --check
# step "lint"        npm run lint
# step "build"       npm run build
# step "tests"       npm test
# step "terraform"   terraform fmt -recursive -check
