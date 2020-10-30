import logging

from pyplanet.apps.config import AppConfig

from pyplanet.contrib.setting import Setting
from pyplanet.apps.core.maniaplanet import callbacks as mp_signals
from pyplanet.contrib.map.exceptions import ModeIncompatible
from pyplanet.utils.times import format_time
from pyplanet.utils.style import STRIP_ALL, style_strip

logger = logging.getLogger(__name__)


class DynatimeApp(AppConfig):
	app_dependencies = ['core.maniaplanet']

	game_dependencies = ['trackmania', 'trackmania_next']

	mode_dependencies = ['TimeAttack']

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.setting_dynatime_active = Setting(
			'dynatime_active', 'Dynatime active', Setting.CAT_BEHAVIOUR, type=bool,
			description='Activate dynamic round timer based on map medal time.',
			default=True
		)

		self.setting_dynatime_announce = Setting(
			'dynatime_announce', 'Dynatime announce', Setting.CAT_BEHAVIOUR, type=bool,
			description='Announce the current time limit at the start of each round.',
			default=True
		)

		self.setting_dynatime_announce_string = Setting(
			'dynatime_announce_string', 'Dynatime announce string', Setting.CAT_BEHAVIOUR, type=str,
			description='Set announce string. Can contain "{map}", "{medal}", "{medal_time}", "{new_time}" to format string.',
			default='$ff0Dynatime set new time limit for map $fff{map}$ff0 to $fff⏳ {new_time}$ff0, based on the {medal}-medal of $fff🏆 {medal_time}'
		)

		self.setting_dynatime_medal = Setting(
			'dynatime_medal', 'Dynatime medal', Setting.CAT_BEHAVIOUR, type=int,
			description='Set medal to determine map time (0: bronze, 1: silver, 2: gold, 3: author).',
			default=3
		)

		self.setting_dynatime_multiplier = Setting(
			'dynatime_multiplier', 'Dynatime multiplier', Setting.CAT_BEHAVIOUR, type=float,
			description='Set multiplier (1.0 - 10.0).',
			default=4.0
		)

		self.setting_dynatime_minimum_time = Setting(
			'dynatime_minimum_time', 'Dynatime minimum time', Setting.CAT_BEHAVIOUR, type=int,
			description='Set minimum time limit.',
			default=180
		)

		self.setting_dynatime_maximum_time = Setting(
			'dynatime_maximum_time', 'Dynatime maximum time', Setting.CAT_BEHAVIOUR, type=int,
			description='Set maximum time limit.',
			default=540
		)

		self.setting_dynatime_formula = Setting(
			'dynatime_formula', 'Dynatime formula', Setting.CAT_BEHAVIOUR, type=str,
			description='Set the formula to calculate the time. Has to contain "{medal_time}" and "{multiplier}" for calculation. Can also contain "{min_time}" and "{max_time}".',
			default='{medal_time} * {multiplier} + {min_time}'
		)

		self.setting_dynatime_round_time = Setting(
			'dynatime_round_time', 'Dynatime round time', Setting.CAT_BEHAVIOUR, type=int,
			description='Rounds time limit to closest value (0: off 1-30: valid).',
			default=15
		)

	async def on_init(self):
		await super().on_init()

	async def on_start(self):
		await super().on_start()

		await self.context.setting.register(
			self.setting_dynatime_active,
			self.setting_dynatime_announce,
			self.setting_dynatime_announce_string,
			self.setting_dynatime_medal,
			self.setting_dynatime_multiplier,
			self.setting_dynatime_minimum_time,
			self.setting_dynatime_maximum_time,
			self.setting_dynatime_formula,
			self.setting_dynatime_round_time
		)

		self.context.signals.listen(mp_signals.map.map_begin, self.map_begin)

	async def on_stop(self):
		await super().on_stop()

	async def on_destroy(self):
		await super().on_destroy()

	async def map_begin(self, map, **kwargs):
		if not await self.setting_dynatime_active.get_value():
			return

		clip = lambda x, l, u: l if x < l else u if x > u else x

		announce_string = await self.setting_dynatime_announce_string.get_value()
		medal = clip(await self.setting_dynatime_medal.get_value(), 0, 3)
		multiplier = clip(await self.setting_dynatime_multiplier.get_value(), 1, 10)
		min_time = max(await self.setting_dynatime_minimum_time.get_value(), 0)
		max_time = max(await self.setting_dynatime_maximum_time.get_value(), 0)
		formula = await self.setting_dynatime_formula.get_value()
		roundto = clip(await self.setting_dynatime_round_time.get_value(), 0, 30)

		mode_settings = await self.instance.mode_manager.get_settings()

		if 'S_TimeLimit' not in mode_settings:
			raise ModeIncompatible('Current mode doesn\'t support Dynatime. Not TimeAttack?')

		if '{medal_time}' not in formula or '{multiplier}' not in formula:
			message = '$0b3Error: Dynatime formula does not contain all necessary variables.'
			logger.error('Dynatime formula does not contain all necessary variables!')
			await self.instance.chat(message)
			return

		medals = ['bronze', 'silver', 'gold', 'author']
		medal_time = eval('map.time_{0}'.format(medals[medal]))
		if map.num_laps > 0:
			medal_time /= map.num_laps

		if max_time <= min_time:
			if min_time <= self.setting_dynatime_minimum_time:
				max_time = self.setting_dynatime_maximum_time.default
			else:
				max_time = int(self.setting_dynatime_maximum_time.default / self.setting_dynatime_minimum_time.default * min_time)
		try:
			timelimit = int(eval(formula.format(
				medal_time = medal_time / 1000,
				multiplier = multiplier,
				min_time = min_time,
				max_time = max_time
			)))
			timelimit = clip(timelimit, min_time, max_time)
			if roundto > 0:
				timelimit = timelimit // 60 * 60 + roundto * ((timelimit % 60 // roundto) + (1 if ((timelimit % 60) % roundto) / roundto >= 0.5 else 0))
			timelimit_ms = timelimit * 1000
		except:
			message = '$0b3Error: Dynatime formula can not be executed successfully.'
			logger.error('Dynatime formula can not be executed successfully!')
			await self.instance.chat(message)
			return

		mode_settings['S_TimeLimit'] = timelimit

		try:
			message = announce_string.format(
				map = style_strip( map.name, STRIP_ALL),
				medal = medals[medal],
				new_time = format_time(time=timelimit_ms, hide_milliseconds=True),
				medal_time = format_time(time=medal_time, hide_milliseconds=True)
			)
		except:
			message = '$0b3Error: Dynatime announce string is not formatted correctly.'
			logger.error('Dynatime announce string is not formatted correctly!')
			await self.instance.chat(message)
			return

		await self.instance.mode_manager.update_settings(mode_settings)

		announce = await self.setting_dynatime_announce.get_value()
		if announce:
			await self.instance.chat(message)
