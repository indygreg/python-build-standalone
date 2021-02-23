// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    anyhow::anyhow,
    std::{convert::TryFrom, str::FromStr},
};

#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct MachOPackedVersion {
    value: u32,
}

impl TryFrom<&str> for MachOPackedVersion {
    type Error = anyhow::Error;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        let parts = value.split('.').collect::<Vec<_>>();

        if parts.len() != 3 {
            return Err(anyhow!("packed version must have 3 components"));
        }

        let major = u32::from_str(parts[0])?;
        let minor = u32::from_str(parts[1])?;
        let subminor = u32::from_str(parts[2])?;

        let value = (major << 16) | ((minor & 0xff) << 8) | (subminor & 0xff);

        Ok(Self { value })
    }
}

impl From<u32> for MachOPackedVersion {
    fn from(value: u32) -> Self {
        Self { value }
    }
}

impl std::fmt::Display for MachOPackedVersion {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let major = self.value >> 16;
        let minor = (self.value >> 8) & 0xff;
        let subminor = self.value & 0xff;

        f.write_str(&format!("{}.{}.{}", major, minor, subminor))
    }
}

/// Describes a mach-o dylib that can be loaded by a distribution.
#[derive(Clone, Debug, PartialEq)]
pub struct MachOAllowedDylib {
    /// Name of the dylib.
    ///
    /// Typically an absolute filesystem path.
    pub name: String,

    /// Maximum compatibility version that can be referenced.
    pub max_compatibility_version: MachOPackedVersion,

    /// Whether the loading of this dylib must be present in the distribution.
    pub required: bool,
}
