# Copyright 2018 Easymov Robotics
# Licensed under the Apache License, Version 2.0

from pathlib import Path
import os
import shutil
import toml

from colcon_cargo.task.cargo import CARGO_EXECUTABLE
from colcon_core.environment import create_environment_scripts
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_core.shell import create_environment_hook, get_command_environment
from colcon_core.task import run
from colcon_core.task import TaskExtensionPoint

logger = colcon_logger.getChild(__name__)


class CargoBuildTask(TaskExtensionPoint):
    """Build Cargo packages."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(TaskExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--cargo-args',
            nargs='*', metavar='*', type=str.lstrip,
            help='Pass arguments to Cargo projects. '
            'Arguments matching other options must be prefixed by a space,\n'
            'e.g. --cargo-args " --help"')

    async def build(
        self, *, additional_hooks=[], skip_hook_creation=False
    ):  # noqa: D102
        pkg = self.context.pkg
        args = self.context.args

        logger.info(
            "Building Cargo package in '{args.path}'".format_map(locals()))

        try:
            env = await get_command_environment(
                'build', args.build_base, self.context.dependencies)
        except RuntimeError as e:
            logger.error(str(e))
            return 1

        rc = await self._build(args, env)
        if rc and rc.returncode:
            return rc.returncode

        additional_hooks += create_environment_hook(
            'cargo_{}_path'.format(pkg.name),
            Path(args.install_base), pkg.name,
            'PATH', os.path.join('lib', self.context.pkg.name, 'bin'),
            mode='prepend')

        if not skip_hook_creation:
            create_environment_scripts(
                pkg, args, additional_hooks=additional_hooks)

    async def _build(self, args, env, *extra_flags, deps={}):
        self.progress('build')

        Path(args.build_base).mkdir(exist_ok=True)

        env['CARGO_TARGET_DIR'] = args.build_base

        root_dir = os.path.join(
            args.install_base, 'lib', self.context.pkg.name)

        # TODO Potentially use empy as the rest of the colcon extensions do
        # caller has specified custom arguments to pass to rustc
        if extra_flags:
            if "RUSTFLAGS" not in env:
                env["RUSTFLAGS"] = ""

            env["RUSTFLAGS"] += " ".join(extra_flags)


        # invoke build step
        if CARGO_EXECUTABLE is None:
            raise RuntimeError("Could not find 'cargo' executable")

        shutil.copytree(args.path, args.build_base, dirs_exist_ok=True)

        # Edit build_dir/Cargo.toml
        with open(Path(args.build_base) / "Cargo.toml") as f:
            cargo_toml = toml.load(f)
        if "dependencies" not in cargo_toml:
            cargo_toml["dependencies"] = {}
        cargo_toml["dependencies"].update(deps)
        with open(Path(args.build_base) / "Cargo.toml", 'w') as f:
            cargo_toml = toml.dump(cargo_toml, f)


        cmd = [
            CARGO_EXECUTABLE, 'install', '--force', '-q',
            '--path', args.build_base,
            '--root', root_dir,
        ]

        return await run(
            self.context, cmd, cwd=args.build_base, env=env)
