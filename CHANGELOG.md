# Changelog

## [1.6.0](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.5.0...v1.6.0) (2026-07-30)


### Features

* **db:** add EMPIAR repo ([#153](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/153)) ([0c03528](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/0c0352807e33053dc05458d3951596ee97cae2d0))
* **docker:** coordinator expose 50051 from coordinator for easy dev ([#140](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/140)) ([d553c87](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/d553c87fac304c94f17fe23a2c10df7bfcb2c908))
* handle dependent endpoints in the scheduler ([#155](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/155)) ([909d4f0](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/909d4f0aaab36d32a80a48151fd2ba66dc0ed1a7))
* **index:** check if indicated index exists ([#114](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/114)) ([a370e8a](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/a370e8a75a8c7baeb3775aab48b0048c2ea42abf))
* **zenodo:** dynamically fetch Zenodo IDs from HAL data ([#147](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/147)) ([bdb456b](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/bdb456b31fdc65981c58188c40538dc837433c9e))

## [1.5.0](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.4.0...v1.5.0) (2026-06-15)


### Features

* add eodc set to onedata ([#134](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/134)) ([9734cba](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/9734cbaa1320719106ea5ae8a16670b219aa7a85))

## [1.4.0](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.3.0...v1.4.0) (2026-06-09)


### Features

* **endpoints:** add DaSCH ([#128](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/128)) ([2c15123](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/2c151233e7e5b95ca26bd28fe09d4ce7c0555111))
* **endpoints:** add MDDB endpoint ([#110](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/110)) ([28ae910](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/28ae91076895ecde312dfb98e6413923746c6392))

## [1.3.0](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.2.1...v1.3.0) (2026-06-08)


### Features

* **skip embedding calc:** add flag to skip recalculating embeddings ([#109](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/109)) ([b742603](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/b742603a6fb91e99531677cd5399c2d36e770107))

## [1.2.1](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.2.0...v1.2.1) (2026-06-05)


### Bug Fixes

* **docker:** copy uv.lock and use --frozen ([#125](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/125)) ([63f4246](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/63f4246d23b5d974376a2bea1c8928682f79d582))
* **gh ci cd:** cache fastembed model  ([#126](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/126)) ([b6b1c25](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/b6b1c25de9fc338ffe63ba4b4e3cf7c788d92d1b))

## [1.2.0](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.1.0...v1.2.0) (2026-06-03)


### Features

* enhance docker publish workflow with manual input ([#123](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/123)) ([bc3928c](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/bc3928c7e39be9b7362bc534c0b418c44daa78c5))

## [1.1.0](https://github.com/EOSC-Data-Commons/metadata-warehouse/compare/v1.0.0...v1.1.0) (2026-06-03)


### Features

* add tool registry ([#88](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/88)) ([6d49e54](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/6d49e544c8d97d325409c6f2009fb411b3d81024))
* commitlint gh action ([#118](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/118)) ([a830f7e](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/a830f7e06eee8b2e0f879618db3291f9c8bdf112))
* **precommit:** add check to prevent invalid commit message formats ([#119](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/119)) ([4d8316f](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/4d8316f77f58705fe89d35b1b57391a9f814b6ae))


### Bug Fixes

* **deps:** remove old redis dep ([#111](https://github.com/EOSC-Data-Commons/metadata-warehouse/issues/111)) ([3932945](https://github.com/EOSC-Data-Commons/metadata-warehouse/commit/3932945d908fb08d2a1d639ec29c17ba7eeef241))

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
