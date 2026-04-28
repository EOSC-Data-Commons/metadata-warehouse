# Changelog

## 1.0.0 (2026-04-28)


### Features

* [[#15](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/15)] sql table design ([#16](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/16)) ([a26f19a](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/a26f19a9eb38c54118be5471f057cb6cc9343122))
* [[#45](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/45)] workflow for a transformation report ([9ecaa2b](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/9ecaa2be1bcb99994f480ab9c590cf887bb060b1))
* add docker volume in `docker-compose.yml` for the search API data, for now mainly to make the conversations logs persistent ([8d97f44](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/8d97f447dcbdbd68e8165ac3dfd47743f32d0dcd))
* add scheduler ([#73](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/73)) ([a39b0db](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/a39b0dbefa6c1235fdab37e4d13b3773d8b42fee))
* flag in scheduler for transforming all harvest_runs ([#93](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/93)) ([b1aeef4](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/b1aeef4ed20aa400209b18bf365385374299c135))
* scheduler works in docker ([#78](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/78)) ([0c60fb8](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/0c60fb8024d86edbcf81f2960afa043a0c8e96cb))
* trigger release gh action ([#96](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/96)) ([ba8cd8b](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/ba8cd8b56570696e822f02247077489b7271b140))


### Bug Fixes

* [[#35](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/35)] use index_name in transformer ([#38](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/38)) ([039c5c3](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/039c5c371eef2e46f972b9fa740c023c75acaabf))
* handle failed harvest_runs ([#80](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/80)) ([926a209](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/926a209005f06d842c5bbfb83f4daa4c9410ddb5))
* make it so the harvester container is manually triggered instead of starting with `docker compose up`. It is not a service, its a script that takes arguments (which are currently missing from the compose). Added instruction to run the harvester container in the readme ([112cd83](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/112cd83be0108e9063a91cd4ed8af02d3f3a3ae6))
* update frontend artifact pruning to include additional file types ([49532b6](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/49532b674b4d2a93f656d97741167871390a17ba))
