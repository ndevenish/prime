import libtbx.load_env
import os

Import("env_base", "env_etc")

env_etc.prime_dist = libtbx.env.dist_path("prime")
env_etc.prime_include = os.path.dirname(env_etc.prime_dist)
env_etc.prime_common_includes = [
    env_etc.prime_include,
    env_etc.libtbx_include,
    env_etc.cctbx_include,
    env_etc.scitbx_include,
    env_etc.chiltbx_include,
    env_etc.omptbx_include,
    env_etc.boost_include,
]

env = env_base.Clone(SHLINKFLAGS=env_etc.shlinkflags)
env.Append(LIBS=["cctbx"] + env_etc.libm)
env_etc.include_registry.append(env=env, paths=env_etc.prime_common_includes)
if env_etc.static_libraries:
    builder = env.StaticLibrary
else:
    builder = env.SharedLibrary

if not env_etc.no_boost_python:
    Import("env_boost_python_ext")
    env_prime_boost_python_ext = env_boost_python_ext.Clone()
    env_prime_boost_python_ext.Prepend(LIBS=["cctbx", "scitbx_boost_python"])
    env_prime_boost_python_ext.SharedLibrary(target="#lib/prime_ext", source="ext.cpp")

    env_etc.include_registry.append(
        env=env_prime_boost_python_ext, paths=env_etc.prime_common_includes
    )
    Export("env_prime_boost_python_ext")
