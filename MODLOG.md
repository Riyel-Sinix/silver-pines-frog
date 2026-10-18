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

## Frog v5 (2026-10-18) — user: the radio/phone portrait becomes the thinking frog; after 10 s of idling play the
## laughing-frog video, with its sound
- Portrait: the face shown on phone calls is the protagonist's dialogue portrait. `sprites-characterportraits_
  assets_all.bundle` holds one Sprite + Texture2D per portrait (Player 237x360; Phone_*, Roberts_radio and the
  NPCs are separate). All 13 `portrait_Player*` textures become a close-up of `frogmod/source/frog_thinking.png`
  (cut from its white app-icon tile; the tile's grey outline means "large light patch" = background; the body
  clipped by the tile's rounded bottom corners is inpainted) on a dark backdrop, RGB24. Disappear_1/2 are
  blurred and darkened, Inner/bleeding/bleeding2 posterized (bleeding with red streaks under the eyes).
- Backpack (status page) photo, added after the user's first look: InGameMenu scene
  `.../StatusContainer/Portrait/Health/PhotoMask/Portrait` is an Image (alpha 0.51, preserve aspect, 312x362 UI
  units) showing `Assets/UI/Health/fine.png` from `team17_auto_base_general_compressed_assets_health.bundle`
  (895x1000 RGB24, next to the polaroid frame). Found by following the Image's m_Sprite to its CAB and a
  header-only scan of all bundles' node names (`scripts/find_cab.py`, 2 s for 2360 bundles). Replaced by the same
  thinking-frog close-up (centred wider, unsharp-masked after the 3.9x upscale).
- Thinking-frog cut-out details: the frog runs off the icon tile's bottom edge only (left/right are white tile),
  the last two rows are blended with the tile's grey outline (repeated from row 253), the edge is eroded 1 px
  (white rim when upscaled), and the rounded tile corners are left as the body's own contour (inpainting them
  from the cream belly left pale wedges).
- Laugh frames: `scripts/laugh_frames.py` cuts the 1280x720 video at 12 fps, 1.5-16.5 s (side view, turn,
  laugh, fall, rolling) plus the fall (13.25-14.6 s) reversed so the frog stands again: 197 frames, mirrored
  to face right. Background = unsaturated pixels (sat < 0.12, |R-B| < 24) connected to the frame border; the
  shadow under the feet is tinted by the frog and matches the cream belly in colour, so within 70 px of the
  lowest point any light, unsaturated pixel connected to the outside is floor too (the rolling frog's eye
  whites are enclosed and stay).
- Everything else is new data in the player clip bundle `team17_auto_base_characters_assets_player.bundle`
  (it holds the Idle_Variants PlayMaker template and was not modded before), built by `scripts/frog_extras.py`:
  - 197 Texture2D (DXT5, 230 px/unit, inline data) + Sprite (full-rect quads via `frogify.apply_sprite`), with
    the Sprite/Texture2D types (type trees + hashes) copied from the main bundle. Frame 0 is scaled to the idle
    frog's height (1.74 units, feet 0.068 above the pivot) and centred; the sideways drift is eased back over
    the 16 get-up frames so the idle that follows does not jump. Path ids = MD5 of the names (reproducible).
  - AnimationClip `Player_FrogLaugh`: a copy of Player_StandingIdleLookAround (bindings: SpriteAnimNodes n5
    x/y/angle, then the SpriteRenderer sprite PPtr curve). The streamed clip is rewritten: -FLT_MAX sentinel
    frame with all four curves, n5 held at the idle loop's first values, one discrete sprite key per frame,
    +inf end frame; curveCount 3 + discreteCurveCount 1. `m_MuscleClipSize` (the runtime blob Unity
    allocates) = 2528 + 4 x streamed words + 8 x m_ValueArrayDelta entries, exact for all 192 player clips.
    No animation events: LookAround's FlashlightRotatedAway/Normal could leave the light turned if interrupted.
  - AudioClip `FrogLaugh`: PCM16 44.1 kHz stereo in a one-sample FSB5 bank (version 1, mode 2, name table
    padded so data starts 32-aligned) in a new `CAB-....resource` node (flags 0); DecompressOnLoad, PCM. No game
    file has an AudioClip, so its type tree comes from UnityPy's TPK (TypeFlags/RefTypeHash filled in, blank
    hash -> Unity reads it through the stored type tree). The bank round-trips through FMOD (fmod_toolkit).
  - Preload range of `Idle_Variants.asset` grows by the 396 new objects; later ranges shift; nothing else moves.
- Idle_Variants: NormalLoop's RandomWait min = max = 9.33 (10 s minus the 0.67 s Player_StandingIdleStart),
  its Trigger goes straight to IdleFlourish_1 (RandomIdleFlourish is skipped). IdleFlourish_1 plays the laugh
  clip (finish event Reset -> Init, so it repeats every ~26 s of standing) and gets two new actions:
  AddComponent("UnityEngine.AudioSource", removeOnExit) and AudioPlay(volume 0.8, one shot FrogLaugh).
  - PlayMaker checks each action's hash against `ActionData.GetActionTypeHashCode`: Jenkins one-at-a-time over
    the UTF-16LE text "FieldType.FullName|" per public field, mod 1e8 (disassembled; reproduces RandomWait
    22830861, BoolTest 12568740, SetBoolValue 65141543, RandomEvent 2087427). AddComponent = 38587512
    (FsmOwnerDefault, FsmString, FsmObject, FsmBool), AudioPlay = 72231297 (FsmOwnerDefault, FsmFloat,
    FsmObject, FsmBool, FsmEvent). Params: FsmEvent names live in stringParams, FsmString in fsmStringParams.
  - ReflectionUtils.GetGlobalType tries typeName + ",Assembly-CSharp"/",PlayMaker"/..., then every loaded
    assembly, then short names in UnityEngine/HutongGames namespaces, so "UnityEngine.AudioSource" resolves.
  - Fsm.OnDisable and RunFSM.OnExit call Fsm.Stop -> ExitState -> OnExit, so leaving idle destroys the
    AudioSource and the sound stops. ComponentAction.UpdateCache re-fetches when the cached component is
    destroyed, so later laughs find the new AudioSource.
- Unity audio: the game plays everything through FMOD (StreamingAssets/Master*.bank) and ships with
  `globalgamemanagers` AudioManager.m_DisableAudio = true (file offset 5752; the AudioListener exists at
  GameManager/AudioListener). frog_extras writes `build/globalgamemanagers` with that byte cleared (found by
  re-serializing the AudioManager). install_frog.bat backs the file up and copies it only when its size matches
  the game's; restore_original.bat puts the backup back only when the sizes match (an updated game keeps its own).
- Bats rewritten: all logic is ASCII and `chcp 65001` runs only right before the messages (each message is a
  label reached by goto). Under code page 65001 cmd misreads the batch file after a line whose %VAR% expands to
  multi-byte text (a Chinese path or Chinese text with a variable) when a later goto skips a line with Chinese
  text: the tail of that line gets executed as a command. Reproduced in small cases; the v4 bats were exposed to
  it when unzipped into a folder with Chinese characters. Also `A || B & C` runs C regardless: parenthesized.
  Tested against a fake game folder (stage under "新建文件夹 (测试)", game under "Program Files (x86)"): install,
  restore, game updated (ggm size differs), wrong folder, no build; through a pipe and in a console window.
- Build: `frog_extras.py frogmod/build` ~10 s (clip bundle 1.1 -> 8.3 MB, portraits 7.1 -> 8.5 MB,
  health 2.2 MB);
  `scripts/verify_extras.py` reads everything back (frame order, 16.42 s, FMOD decode, template, preload table,
  only AssetBundle + template changed among the original objects). Installed 2026-10-18 (210 patch bundles +
  globalgamemanagers; originals in frogmod/backup). Player.log is in
  `%USERPROFILE%\AppData\LocalLow\Wych Elm\Silver Pines\`.
- Checked in game by the user (2026-10-18): the laugh, its sound and the dialogue portrait work ("测试结果很棒");
  that session's Player.log shows nothing from the new objects (no class, action or component errors). The
  backpack photo came after that test: installed, not yet seen in game.
