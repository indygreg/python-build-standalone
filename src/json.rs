// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    anyhow::Result,
    serde::Deserialize,
    std::collections::{BTreeMap, BTreeSet, HashMap},
};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LinkEntry {
    pub name: String,
    pub path_static: Option<String>,
    pub path_dynamic: Option<String>,
    pub framework: Option<bool>,
    pub system: Option<bool>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PythonBuildExtensionInfo {
    pub in_core: bool,
    pub init_fn: String,
    pub licenses: Option<Vec<String>>,
    pub license_paths: Option<Vec<String>>,
    pub license_public_domain: Option<bool>,
    pub links: Vec<LinkEntry>,
    pub objs: Vec<String>,
    pub required: bool,
    pub static_lib: Option<String>,
    pub shared_lib: Option<String>,
    pub variant: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PythonBuildCoreInfo {
    pub objs: Vec<String>,
    pub links: Vec<LinkEntry>,
    pub shared_lib: Option<String>,
    pub static_lib: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PythonBuildInfo {
    pub core: PythonBuildCoreInfo,
    pub extensions: BTreeMap<String, Vec<PythonBuildExtensionInfo>>,
    pub inittab_object: String,
    pub inittab_source: String,
    pub inittab_cflags: Vec<String>,
    pub object_file_format: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PythonJsonMain {
    pub apple_sdk_canonical_name: Option<String>,
    pub apple_sdk_deployment_target: Option<String>,
    pub apple_sdk_platform: Option<String>,
    pub apple_sdk_version: Option<String>,
    pub build_info: PythonBuildInfo,
    pub crt_features: Vec<String>,
    pub libpython_link_mode: String,
    pub licenses: Option<Vec<String>>,
    pub license_path: Option<String>,
    pub optimizations: String,
    pub python_abi_tag: Option<String>,
    pub python_bytecode_magic_number: String,
    pub python_config_vars: HashMap<String, String>,
    pub python_exe: String,
    pub python_extension_module_loading: Vec<String>,
    pub python_implementation_cache_tag: String,
    pub python_implementation_hex_version: u64,
    pub python_implementation_name: String,
    pub python_implementation_version: Vec<String>,
    pub python_major_minor_version: String,
    pub python_paths_abstract: HashMap<String, String>,
    pub python_paths: HashMap<String, String>,
    pub python_platform_tag: String,
    pub python_stdlib_platform_config: Option<String>,
    pub python_stdlib_test_packages: Vec<String>,
    pub python_suffixes: HashMap<String, Vec<String>>,
    pub python_symbol_visibility: String,
    pub python_tag: String,
    pub python_version: String,
    pub target_triple: String,
    pub run_tests: String,
    pub tcl_library_path: Option<String>,
    pub tcl_library_paths: Option<Vec<String>>,
    pub version: String,
}

impl PythonJsonMain {
    pub fn all_object_paths(&self) -> BTreeSet<&str> {
        let mut res = BTreeSet::from_iter(self.build_info.core.objs.iter().map(|x| x.as_str()));

        for entries in self.build_info.extensions.values() {
            for ext in entries {
                res.extend(ext.objs.iter().map(|x| x.as_str()));
            }
        }

        res
    }
}

pub fn parse_python_json(json_data: &[u8]) -> Result<PythonJsonMain> {
    let v: PythonJsonMain = serde_json::from_slice(json_data)?;

    Ok(v)
}
