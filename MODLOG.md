# Silver Pines CE table — MODLOG

## Target
- `D:\Games\Silver Pines\Carpenter.exe`, Unity 6000.3.15f1, IL2CPP, metadata v39, Wych Elm / Team17.
- Saves: `%USERPROFILE%\AppData\LocalLow\Wych Elm\Silver Pines\<account id>\` (2 slots).
- Display settings: `HKCU\Software\Wych Elm\Silver Pines` (fullscreen mode 1, 2560x1600).

## Backups (restore after any test)
- Saves: a zip of the saves folder taken before testing (unzip back to the saves folder).
- Registry: `_backup\silverpines-display.reg` (`reg import`).

## Tools
- Il2CppDumper c01ns v39.1 (`_downloads/`), output in `_dump/` (dump.cs, script.json, il2cpp.h).
- `scripts/`: parse_dump.py, show_type.py, build_symbols.py, disasm.py (capstone + .pdata bounds),
  xrefs.py (RIP-relative + call xrefs), aobcheck.py + patterns.json (uniqueness check).
- Run Python with `python -P -E` (capstone/numpy live in user site-packages, `-I` hides them).

## Facts (RVAs in GameAssembly.dll, this build)
- GameDebugCommands_TypeInfo slot 0x44500E8; static bools: +2 CHEAT_INFINITE_AMMO, +3 CHEAT_INFINITE_STAMINA,
  +4 CHEAT_INVINCIBLE, +5 CHEAT_MASTER_KEY, +6 CHEAT_MAP_SHOW_EVERYTHING, +8 ALWAYS_WEAKPOINT_HIT, +0 SKIP_STORY.
- CharacterHealth_TypeInfo slot 0x44A8520; static +0 JESUS_PLAYER (lethal hit -> health refilled to max).
- GlobalReferences_TypeInfo slot 0x4451EF8; static +0 m_instance; instance +0x50 MainInventory;
  PlayerMainInventory +0x100 m_money, +0xC0 equipped primary, +0xC8 equipped melee.
- Il2CppClass: +0x10 name, +0xB8 static_fields. Uninitialised slots hold an odd encoded token.
- Patches: RemoveDurability subss @0x6DFDC4, inlined copy @0x6E1865, power drain subss @0x7CA637,
  RemoveMoney sub @0x6E79BB, one-hit-kill hook after IsPlayer @0x7C1FFB (non-player je -> 0x7C2055).
- set_Health clamps to [m_minimumHealth, MaxHealth] so 999999 damage is safe for scripted bosses.
- NG+ unlocks come from save data (PersistentData.IsGameUnlockEnabled) — deliberately not touched.

## Test harness
- Private CE copy `_cetest/CE74` with `autorun/zz_sp_rpc.lua` (file RPC: `_cetest/rpc/cmd.lua` -> `out.txt`),
  driven by `scripts/cerpc.sh`.

## Verification (2026-10-16, live game + private CE 7.4 copy via file RPC)
- Activate: all 8 symbols resolved to the expected RVAs; GDC/GR/CH slots initialised, class names validated.
- Every child script enable/disable round-trip OK: flags write exactly one byte and clear to 0;
  code patches apply and restore byte-exactly; OHK cave disassembled correct (jmp 0x7C2055 / return 0x7C2006).
- Money pointer `[[[[SP_GR_TI]+B8]+0]+50]+100` valid in game (read 3).
- Not exercised in combat: invincible/OHK/durability/flashlight effects (verified by code reading + memory only).
- The cheat bools are DebugConsole variables ([DebugCommand("invincible", ...)] etc.); no game code writes them.
- User stopped the automated test to try the table themselves; game left running (launched windowed 1280x800).
  Saves NOT restored (user may be playing). Display registry backup: `_backup\silverpines-display.reg`.

## Frog (奶蛙) player-model replacement (2026-10-17)
- Player art = frame-by-frame sprites: `team17_auto_base_characters_compressed_assets_player.bundle`
  (1929 Sprites, one DXT5 Texture2D each, 1.31 GB uncompressed, LZ4HC, Unity 6 UnityFS v8).
  Sprites use Tight meshes (46-62 verts); UV stream is zero, Unity derives UVs from positions via
  `m_RD.uvTransform = (ppu, pivot_px_x, ppu, pivot_px_y)`. settingsRaw bit 6 = meshType (1 = Tight).
- Character faces right; turn clips go right -> front -> left; `PlayerRun00_flipped` faces left.
- Aiming = arm-less body frames + separate `Head` (player_aim_head) / arm sprites (PlayerArm*, arm_*).
- Builder: `scripts/build_frog_bundle.py` (silhouette PCA: upright bob/squash/stretch, lean, lying with head
  away from the pivot; full-rect quad meshes; canvas grows to multiples of 4; arms recoloured; head hidden).
- Source image: `frogmod/frog_source.png` -> `scripts/cutout.py` -> `frogmod/frog_cutout.png` (101x200).
- Addressables 2.9.1 binary catalog. zlib CRC32 of the bundle data is NOT found in catalog.bin, so whether CRC
  is enforced is unknown -> test in game first; fallback = AddressablesTools v3 `patchcrc` (rewrites in place,
  keeps `.old`; output is 470 bytes larger than the original).
- Install/restore: `frogmod/install_frog.bat`, `frogmod/restore_original.bat` (back up to `frogmod/backup/`).

## Frog v2 (2026-10-17) — fixes for: feet out of sync, human model when raising a gun, four arms
- Root causes: legs were one static image; rifle-draw / reload-arm / aim-arm frames live in ~210 *patch* bundles
  that v1 never touched (PlayerRifleDrawArms even carries the human head); aiming draws an arm-less body plus
  code-driven arm sprites (CharacterAiming: Arm Front/Arm Rear/Head renderers), so a frog with its own arms = 4 arms.
- `scripts/clip_map.py` -> `_dump/clip_map.txt`: every AnimationClip's sprites (compiled clips: genericBindings
  isPPtrCurve + pptrCurveMapping; path = crc32 of the transform path; "<root>" = the separate Arm Sprite animator).
  Pairs: Reload*/Reload*_Arms, CrouchReloadRevolver*/_Arms, DrawRifle/DrawRifleArm, ReloadShotgun*/…Arm,
  DrawRifleBlocked/…Arm; DrawGunCutsceneArm only in a cutscene. Throw arms: debug playercharacterdummy bundle.
- Builder v2: `scripts/frogify.py` (replaces build_frog_bundle.py). Classes: overlay arms recoloured (flat palette:
  skin (136,112,96) -> olive hand, sleeve/shadow -> yellow), arm-less frog for bodies shown with overlays,
  hidden: player_aim_head, PlayerDrawGunArm, PlayerRifleTurnArms, PlayerAimShotgunPumpArm.
- Legs: pre-pass measures both feet of every upright frame (torso-relative, world units); plan_legs swaps the
  frog's near/far leg at each crossing so cycles alternate; LEG_K=1 (frog feet land on his feet), soft limit at
  0.75 x leg length; legs sheared about the hip. Moderate leans (<35°) shear-tilt only the body; lying poses
  rotate the whole frog, head end found from skin pixels (face/hands), length = silhouette major axis.
- Parts (`scripts/frog_parts.py`): defringe (white halo), arm-less body without stub/crease, body overlaps the leg
  tops by 5 feathered rows (no hip seam). Resampling on straight alpha over bled layers (no white specks).
- Previews: `frogify.py strip` (frog over ghost of original, pivots aligned), `pairs` (body+overlay stacked),
  `preview`. Verification: `verify_frog_bundle.py` (main: 1869 quads OK, 3 weapon false positives),
  `verify_patches.py` (207 bundles load, 141 redrawn quads OK, 87 overlays unchanged size/rect).
- Output: `frogmod/build/` main bundle (280 MB) + `build/patches/` 207 bundles + bundles.txt.
  Original patch bundles backed up in `frogmod/backup/patches/` (214). install_frog.bat / restore_original.bat
  handle all of them (use %SystemRoot%\System32\find.exe — Git's find shadows it when run from bash).
- In game (windowed 1280x800): frog loads; aiming a rifle shows arm-less frog + two yellow arms, no human parts.
  The user took over with a gamepad mid-test, so walking was checked only in the strips (_shots/strip_*.png).

## Frog v3 (2026-10-17) — user: melee weapons show no arms; add an arm swing when running
- `scripts/clip_curves.py` decodes the compiled clips (streamed cubic keys + dense + constant curves, bindings by
  CRC32 of "m_node6.x" etc.) -> `_dump/sprite_nodes.json`: per body sprite the SpriteAnimNodes values. Node
  convention: pixels from the sprite pivot, x right, **y down**; angle in degrees in that y-down space.
  SpriteAnimNodeType: 0 AnimRoot, 1 DamageableZone (Head), 2 HurtBox, 4 AimJoint (shoulder), 5 Flashlight (chest),
  6 Weapon (grip, WeaponsAnimNode follows it), 7 FootPosition. Walk/run clips key no hand node.
- Frames with node 6 (swings, knife combos, throws, pry-open, manhole key, draw/turn gun, shotgun pump, rifle
  turn; not the overlay/arm-less groups) now use the arm-less body plus drawn frog arms: two-bone IK from the
  frog's shoulder to the grip (two-handed groups put the far hand further along the weapon).
- Run groups (PlayerRun/RunStart/RunHurt/RunStop/RunTurn/StumbleRun) swing both arms opposite to the same-side
  leg from the leg plan (rest 10°, ±45°, elbow 75°). Walking keeps the hands on the belly.
- Arms are drawn (draw_arm: shaded capsules + olive fist, 3x supersampled); far arm behind the body.

## Frog v4 (2026-10-18) — user: stairs-down from the three-view sheet; 惊鸿一瞥 every few seconds; swim arm strokes;
## better climbing; walking feet must step forward
- `scripts/frog_views.py` builds front/back/glance parts from `frogmod/source/frog_turnaround.png` (front crop
  (80,18,164,184), back (164,18,258,184)) and `frog_glance.png` (head transplanted onto the side body with a
  colour transfer) -> `frogmod/parts/front_*`, `back_*`, `body_glance`, `views.json` (sizes, hip rows, shoulders).
- Views: back for PlayerEnterIntoFrontDoor / PlayerStairsDownInward / PlayerLadderClimb (+ LadderEnter/Exit
  while no face shows); front for PlayerWalkToCamera / EnterThroughDoorFront / PlayerTurn (+ probes: face-skin
  share of the top 15% of the silhouette >= 0.38). PlayerStairsDownInward is referenced by no clip; the game's
  stairs clips are Player_StairsWalkDown/Up (side view) and the legacy Player_StairsTurn (front frames 1-3).
- 惊鸿一瞥: Player_StandingIdleLoop (2.92 s, PlayerIdle_v2_loop 0-8) frames 5-6, so once per idle loop; plus the
  look-around frames that face the camera (PlayerIdleLook 7-15). The near / far eye of the transplanted head is
  bulged x1.4 / x1.6 (`frog_views.bulge`), otherwise the glance is only a few pixels different at game size.
- Walking (the feet seemed to step backwards): passing frames are interpolated (fill_crossings) and the side legs
  were rebuilt. The cut-out's two legs hang from opposite sides of the belly, so a stride with the near foot
  behind crossed them in an X. Both legs are now the cut-out's profile front leg (its back leg is a stubby 3/4
  foot), the far one shaded x0.8 and placed at the back leg's rest; `leg_slides` slides the leg tops together as
  the feet meet and swaps them once the near foot is behind, so they hinge like a side view. `round_bottom`
  rounds the body's flat-cut underside while the tops are moved in. The cream streak, the soft ground shadow
  and the other foot's stray toes under the front foot are removed (`side_legs`).
- Swimming: rotated PlayerSwimLoop frames draw crawl strokes (hands circle the shoulder, half a stroke apart,
  phase = frame in the 10-frame clip); upright PlayerSwimIdle (treading water) paddles in front of the chest.
  Swim frames take the head end from the facing direction (SwimLoop06's mid-stroke hand fooled head_direction).
- Climbing: ladder = back view, hands up the ladder (the hand opposite the higher foot higher); ledge groups hang
  from the topmost hand (HANG_MIN_HEIGHT 1.6, so LedgeGrabSwing 05/08 and LedgeUpHigh 03 no longer drop the
  arm mid-swing); PlayerClimbRope finds both hands (find_hands) and puts the frog's hands on them, body hanging
  below the lower hand with the belly just behind the rope.
- Build: main 1866 body / 24 overlay / 22 hidden (273 MB); patches 207 bundles. verify_frog_bundle: 1869 quads
  OK, same 3 weapon false positives; verify_patches: 207 load, 141 quads, 87 overlays, 0 problems. Installed
  2026-10-18 (second v4 build, with the swim and glance fixes), hashes match. v3 build kept in
  `frogmod/build_v3/`. Not yet checked in game. `scripts/showcase.py` renders frog-only rows per feature
  (_shots/v4_showcase.jpg).
- Probes added: `scripts/hang_probe.py` (hang/swim measurements), `scripts/view_list.py` (view per frame).
