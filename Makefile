.PHONY: submodule-init submodule-update submodule-status reset-projects

submodule-init:
	git submodule update --init --recursive

submodule-update:
	git submodule update --remote

submodule-status:
	git submodule status

reset-projects:
	git submodule foreach --recursive 'git checkout $(git config -f $toplevel/.gitmodules submodule.$name.branch || echo main)'
