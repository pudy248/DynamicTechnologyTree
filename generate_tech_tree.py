"""
Stellaris Dynamic Technology Tree Generator
"""

import re
import configparser
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List
from collections import Counter


@dataclass
class Technology:
    tech_id: str
    research_area: str = ""
    tier_level: int = 0
    prerequisite_tech_ids: List[str] = field(default_factory=list)
    unlocked_tech_ids: List[str] = field(default_factory=list)
    is_dangerous_tech: bool = False
    is_repeatable_tech: bool = False
    research_cost: str = ""
    tech_categories: List[str] = field(default_factory=list)
    unlock_conditions: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        dangerous_tech_list = {
            "tech_synthetic_workers", "tech_sapient_ai", "tech_positronic_ai",
            "tech_mega_engineering", "tech_colossus", "tech_juggernaut"
        }
        self.is_dangerous_tech = self.tech_id in dangerous_tech_list
        self.is_repeatable_tech = "repeatable" in self.tech_id


class TechTreeGenerator:
    
    RESEARCH_AREA_ICONS = {
        "physics": "£physics£",
        "engineering": "£engineering£", 
        "society": "£society£"
    }
    
    SUPPORTED_LANGUAGES = {
        "english": "l_english",
        "simp_chinese": "l_simp_chinese"
    }
    
    LOCALIZATION_STRINGS = {
        "english": {
            "title": "Technology Tree",
            "top_level": "Maximum Level Reached",
            "requires": "Requires",
            "tier_label": "Tier:"
        },
        "simp_chinese": {
            "title": "科技树",
            "top_level": "已达到顶级", 
            "requires": "还需",
            "tier_label": "级别:"
        }
    }
    
    TECH_DEFINITION_REGEX = re.compile(r'(?m)^(\w+)\s*=\s*\{')
    PREREQUISITES_REGEX = re.compile(r'prerequisites\s*=\s*\{')
    COST_REGEX = re.compile(r'cost\s*=\s*([@\w\d]+)')
    CATEGORY_REGEX = re.compile(r'category\s*=\s*\{')
    POTENTIAL_REGEX = re.compile(r'(?:potential|starting_potential)\s*=\s*\{')
    DANGEROUS_TECH_REGEX = re.compile(r'is_dangerous\s*=\s*yes')
    REPEATABLE_TECH_REGEX = re.compile(r'is_repeatable\s*=\s*yes')
    RESEARCH_AREA_REGEX = re.compile(r'area\s*=\s*(\w+)')
    TIER_REGEX = re.compile(r'tier\s*=\s*(\d+)')
    STARTING_TECH_REGEX = re.compile(r'start_tech\s*=\s*yes')
    TECH_ID_REGEX = re.compile(r'"([^"]+)"|(\w+)')
    WORD_REGEX = re.compile(r'[\w_]+')
    
    DESCRIPTION_LOCALIZATION_REGEX = re.compile(r'^\s*([a-zA-Z0-9_]+_desc):(?:\d+)?\s*"([^"]*(?:\\.[^"]*)*)"', re.IGNORECASE)
    WHITESPACE_CLEANUP_REGEX = re.compile(r'\s+')

    def __init__(self, config_path: str):
        self.all_technologies: Dict[str, Technology] = {}
        self.base_game_tech_ids = set()
        self.tech_descriptions: Dict[str, Dict[str, str]] = {}
        self.base_game_path, self.mod_folder_path, self.mod_filter_settings, self.localization_mod_list = self._load_configuration(config_path)
        
        self.current_mod_folder_name = Path(__file__).parent.name

        
    def _load_configuration(self, config_path: str) -> tuple:
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')
        
        try:
            base_path = config.get('paths', 'base_game_path')
            mod_path = config.get('paths', 'mod_folder_path')
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            raise ValueError(f"配置文件缺少必需的配置项: {e}")
        
        mod_filter_settings = {'enable_filter': False, 'ignored_mods': set(), 'included_mods': set()}
        
        if config.has_section('mod_filter'):
            mod_filter_settings['enable_filter'] = config.getboolean('mod_filter', 'enable_mod_filter', fallback=False)
            
            ignored_str = config.get('mod_filter', 'ignored_mods', fallback='').strip()
            if ignored_str:
                mod_filter_settings['ignored_mods'] = {mod.strip() for mod in ignored_str.split(',') if mod.strip()}
            
            included_str = config.get('mod_filter', 'included_mods', fallback='').strip()
            if included_str:
                mod_filter_settings['included_mods'] = {mod.strip() for mod in included_str.split(',') if mod.strip()}
        
        localization_mod_list = []
        if config.has_section('chinese_localization'):
            centralized_str = config.get('chinese_localization', 'centralized_mods', fallback='').strip()
            if centralized_str:
                localization_mod_list = [mod.strip() for mod in centralized_str.split(',') if mod.strip()]
        
        return base_path, mod_path, mod_filter_settings, localization_mod_list
    
    def _should_include_mod(self, mod_id: str) -> bool:
        if mod_id == self.current_mod_folder_name:
            return False
            
        if not self.mod_filter_settings['enable_filter']:
            return True
        
        if self.mod_filter_settings['included_mods']:
            return mod_id in self.mod_filter_settings['included_mods']
        
        if self.mod_filter_settings['ignored_mods']:
            return mod_id not in self.mod_filter_settings['ignored_mods']
        
        return True
    
    def _should_scan_mod_localization(self, mod_id: str) -> bool:
        if mod_id in self.localization_mod_list:
            return False
            
        return self._should_include_mod(mod_id)
    
    def _display_mod_filter_info(self):
        if self.mod_filter_settings['enable_filter']:
            print("MOD过滤: 已启用")
            if self.mod_filter_settings['included_mods']:
                print(f"  仅扫描MOD: {', '.join(sorted(self.mod_filter_settings['included_mods']))}")
            elif self.mod_filter_settings['ignored_mods']:
                print(f"  忽略MOD: {', '.join(sorted(self.mod_filter_settings['ignored_mods']))}")
        else:
            print("MOD过滤: 未启用")
        
        if self.localization_mod_list:
            print(f"已配置汉化MOD: {', '.join(self.localization_mod_list)}")
        else:
            print("汉化MOD: 未配置")
        
    def scan_all_technology_files(self):
        self._display_mod_filter_info()
        
        self._scan_technology_path(Path(self.base_game_path) / "common" / "technology", "游戏本体科技文件")
        self.base_game_tech_ids = set(self.all_technologies.keys())
        
        mod_folder = Path(self.mod_folder_path)
        if mod_folder.exists():
            scanned_count = 0
            
            for mod_dir in mod_folder.iterdir():
                if mod_dir.is_dir():
                    mod_id = mod_dir.name
                    
                    if self._should_include_mod(mod_id):
                        mod_tech_path = mod_dir / "common" / "technology"
                        if mod_tech_path.exists():
                            new_techs = self._scan_technology_path(mod_tech_path, f"MOD科技文件 {mod_id}")
                            if new_techs > 0:
                                scanned_count += 1
        
    def _scan_technology_path(self, path: Path, description: str) -> int:
        if not path.exists():
            return 0
            
        before_count = len(self.all_technologies)
        
        for file_path in path.glob("*.txt"):
            try:
                self._parse_single_tech_file(file_path)
            except Exception:
                pass
                
        return len(self.all_technologies) - before_count
                    
    def _parse_single_tech_file(self, filepath: Path):
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
            
        content = self._remove_comments_from_content(content)
        
        for match in self.TECH_DEFINITION_REGEX.finditer(content):
            tech_id = match.group(1)
            tech_block = self._extract_braced_block(content, match.end())
            
            if tech_block and tech_id not in self.all_technologies:
                self.all_technologies[tech_id] = Technology(tech_id)
                self._parse_tech_block_content(self.all_technologies[tech_id], tech_block)

    def _read_file_with_encoding(self, filepath: Path) -> str:
        try:
            return filepath.read_text(encoding='utf-8-sig', errors='ignore')
        except:
            try:
                return filepath.read_text(encoding='utf-8', errors='ignore')
            except:
                return ""

    def _remove_comments_from_content(self, content: str) -> str:
        lines = []
        for line in content.splitlines():
            if line.lstrip().startswith('#'):
                continue
            if '#' in line:
                line = line.split('#', 1)[0]
            lines.append(line)
        return '\n'.join(lines)

    def _extract_braced_block(self, content: str, start_pos: int) -> str:
        brace_depth = 1
        for i, char in enumerate(content[start_pos:], start_pos):
            if char == '{':
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    return content[start_pos:i]
        return ""

    def _parse_tech_block_content(self, tech: Technology, content: str):
        if area_match := self.RESEARCH_AREA_REGEX.search(content):
            tech.research_area = area_match.group(1)
        
        if tier_match := self.TIER_REGEX.search(content):
            tech.tier_level = int(tier_match.group(1))
        
        if m := self.PREREQUISITES_REGEX.search(content):
            block = self._extract_braced_block(content, m.end())
            tech_matches = self.TECH_ID_REGEX.findall(block)
            tech.prerequisite_tech_ids = [m_id if m_id else w_id for m_id, w_id in tech_matches]
        
        if self.STARTING_TECH_REGEX.search(content):
            tech.prerequisite_tech_ids = []
            
        if cost_match := self.COST_REGEX.search(content):
            tech.research_cost = cost_match.group(1)
            
        if cat_m := self.CATEGORY_REGEX.search(content):
            cat_block = self._extract_braced_block(content, cat_m.end())
            tech.tech_categories = [c for c in self.WORD_REGEX.findall(cat_block)]
            
        if pot_m := self.POTENTIAL_REGEX.search(content):
            pot_block = self._extract_braced_block(content, pot_m.end())
            tech.unlock_conditions = [p for p in self.WORD_REGEX.findall(pot_block)]
        
        tech.is_dangerous_tech = tech.is_dangerous_tech or bool(self.DANGEROUS_TECH_REGEX.search(content))
        tech.is_repeatable_tech = tech.is_repeatable_tech or bool(self.REPEATABLE_TECH_REGEX.search(content))
    
    def scan_all_tech_descriptions(self):
        self._scan_english_tech_descriptions()
        self._scan_chinese_tech_descriptions()

    def _scan_english_tech_descriptions(self):
        base_localisation_path = Path(self.base_game_path) / "localisation"
        if base_localisation_path.exists():
            files = list(base_localisation_path.rglob("*l_english*.yml"))
            if files:
                for yml_file in files:
                    try:
                        self._parse_english_description_file(yml_file, is_base_game=True)
                    except Exception:
                        pass
        
        mod_folder = Path(self.mod_folder_path)
        if mod_folder.exists():
            for mod_dir in mod_folder.iterdir():
                if mod_dir.is_dir() and self._should_include_mod(mod_dir.name):
                    mod_localisation_path = mod_dir / "localisation"
                    if mod_localisation_path.exists():
                        self._scan_mod_english_localization_files(mod_localisation_path)

    def _scan_chinese_tech_descriptions(self):
        found_chinese_descriptions = {}
        
        base_localisation_path = Path(self.base_game_path) / "localisation"
        if base_localisation_path.exists():
            files = list(base_localisation_path.rglob("*l_simp_chinese*.yml"))
            if files:
                for yml_file in files:
                    try:
                        self._parse_chinese_description_file(yml_file, found_chinese_descriptions)
                    except Exception:
                        pass
        
        mod_folder = Path(self.mod_folder_path)
        if mod_folder.exists():
            if self.localization_mod_list:
                for localization_mod_id in self.localization_mod_list:
                    localization_mod_path = mod_folder / localization_mod_id
                    if localization_mod_path.exists():
                        if self._should_include_mod(localization_mod_id):
                            self._scan_chinese_localization_files(localization_mod_path / "localisation", found_chinese_descriptions)
                        else:
                            print(f"信息：汉化MOD已配置但被过滤规则排除: {localization_mod_id}")
                    else:
                        print(f"警告：配置的汉化MOD不存在: {localization_mod_id}")

            for mod_dir in mod_folder.iterdir():
                if mod_dir.is_dir() and self._should_scan_mod_localization(mod_dir.name):
                    mod_localisation_path = mod_dir / "localisation"
                    if mod_localisation_path.exists():
                        self._scan_chinese_localization_files(mod_localisation_path, found_chinese_descriptions)

    def _scan_mod_english_localization_files(self, localisation_path: Path):
        try:
            files = list(localisation_path.rglob("*l_english*.yml"))
            if files:
                for yml_file in files:
                    try:
                        self._parse_english_description_file(yml_file, is_base_game=False)
                    except Exception:
                        pass
        except Exception:
            pass

    def _scan_chinese_localization_files(self, localisation_path: Path, found_descriptions: dict) -> int:
        if not localisation_path or not localisation_path.exists():
            return 0
            
        found_count = 0
        try:
            chinese_files = list(localisation_path.rglob("*l_simp_chinese*.yml"))
            for yml_file in chinese_files:
                try:
                    found_count += self._parse_chinese_description_file(yml_file, found_descriptions)
                except Exception:
                    pass
        except Exception:
            pass
        return found_count

    def _parse_chinese_description_file(self, filepath: Path, found_descriptions: dict) -> int:
        content = self._read_file_with_encoding(filepath)
        if not content:
            return 0
        
        found_count = 0
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if match:
                desc_key = match.group(1)
                description = self._clean_description_text(match.group(2))
                tech_id = desc_key.replace('_desc', '')
                
                if (tech_id in self.all_technologies and tech_id not in found_descriptions):
                    if tech_id not in self.tech_descriptions:
                        self.tech_descriptions[tech_id] = {}
                    
                    self.tech_descriptions[tech_id]["simp_chinese"] = description
                    found_descriptions[tech_id] = True
                    found_count += 1
        
        return found_count

    def _parse_english_description_file(self, filepath: Path, is_base_game: bool):
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if match:
                desc_key = match.group(1)
                description = self._clean_description_text(match.group(2))
                tech_id = desc_key.replace('_desc', '')
                
                if tech_id in self.all_technologies:
                    if tech_id not in self.tech_descriptions:
                        self.tech_descriptions[tech_id] = {}

                    if is_base_game:
                        self.tech_descriptions[tech_id]["english"] = description
                    else:
                        self.tech_descriptions[tech_id]["english"] = description
                        self.tech_descriptions[tech_id]["simp_chinese"] = description

    def _clean_description_text(self, description: str) -> str:
        description = description.replace('\\"', '"').replace('\\n', ' ').replace('\\t', ' ')
        return self.WHITESPACE_CLEANUP_REGEX.sub(' ', description).strip()
            
    def build_technology_tree_relationships(self):
        for tech in self.all_technologies.values():
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id in self.all_technologies:
                    prereq_tech = self.all_technologies[prereq_id]
                    if tech.tech_id not in prereq_tech.unlocked_tech_ids:
                        prereq_tech.unlocked_tech_ids.append(tech.tech_id)
                        
    def _format_tech_tree_entry(self, tech_id: str, indent_level: int = 1, current_prereq: str = None, lang_code: str = "simp_chinese") -> str:
        if tech_id not in self.all_technologies:
            return ""
            
        tech = self.all_technologies[tech_id]
        indent = "    " * indent_level
        
        area_icon = self.RESEARCH_AREA_ICONS.get(tech.research_area, "")
        
        if tech.is_dangerous_tech:
            formatted = f"({tech.tier_level})['technology:{tech_id}', {area_icon}§R${tech_id}$§!]"
        elif tech.tier_level >= 5 or tech.is_repeatable_tech:
            formatted = f"({tech.tier_level})['technology:{tech_id}', {area_icon}§M${tech_id}$§!]"
        else:
            formatted = f"({tech.tier_level})['technology:{tech_id}', {area_icon}§W${tech_id}$§!]"
        
        additional_prereqs = []
        if current_prereq and len(tech.prerequisite_tech_ids) > 1:
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id != current_prereq and prereq_id in self.all_technologies:
                    prereq_tech = self.all_technologies[prereq_id]
                    prereq_area_icon = self.RESEARCH_AREA_ICONS.get(prereq_tech.research_area, "")
                    
                    if prereq_tech.is_dangerous_tech:
                        prereq_formatted = f"({prereq_tech.tier_level})['technology:{prereq_id}', {prereq_area_icon}§R${prereq_id}$§!]"
                    elif prereq_tech.tier_level >= 5 or prereq_tech.is_repeatable_tech:
                        prereq_formatted = f"({prereq_tech.tier_level})['technology:{prereq_id}', {prereq_area_icon}§M${prereq_id}$§!]"
                    else:
                        prereq_formatted = f"({prereq_tech.tier_level})['technology:{prereq_id}', {prereq_area_icon}§W${prereq_id}$§!]"
                    
                    additional_prereqs.append(prereq_formatted)
        
        entry = f"{indent}|--{formatted}"
        if additional_prereqs:
            prereq_text = " , ".join(additional_prereqs)
            requires_text = self.LOCALIZATION_STRINGS[lang_code]["requires"]
            entry += f" [§R{requires_text}§! {prereq_text}]"
        
        return entry
        
    def _build_tech_subtree(self, tech_id: str, current_depth: int = 0, parent_tech_id: str = None, lang_code: str = "simp_chinese") -> List[str]:
        if tech_id not in self.all_technologies:
            return []
        
        tech = self.all_technologies[tech_id]
        lines = []
        
        unlocked_techs = sorted(tech.unlocked_tech_ids, key=lambda tid: (
            self.all_technologies.get(tid, Technology(tid)).tier_level, tid
        ))
        
        for unlock_id in unlocked_techs:
            tech_line = self._format_tech_tree_entry(unlock_id, current_depth + 1, tech_id, lang_code)
            if tech_line:
                lines.append(tech_line)
            
            subtree_lines = self._build_tech_subtree(unlock_id, current_depth + 1, unlock_id, lang_code)
            lines.extend(subtree_lines)
                
        return lines
        
    def generate_tech_tree_content(self, tech_id: str, lang_code: str = "simp_chinese") -> str:
        if tech_id not in self.all_technologies:
            return ""
            
        tree_lines = self._build_tech_subtree(tech_id, current_depth=0, parent_tech_id=tech_id, lang_code=lang_code)
        if not tree_lines:
            return "\\n\\n§H$technology_tree_title$§!\\n§Y$tech_tree_max_level$§!"
            
        header = "\\n\\n§H$technology_tree_title$§!"
        content = header + "\\n" + "\\n".join(tree_lines)
        return content
        
    def _get_output_file_paths(self, lang_code: str, filename: str) -> List[Path]:
        base = Path("output/localisation/")
        paths = [
            base / filename,
            base / filename,
            base / lang_code / filename,
            base / "replace" / filename,
            base / lang_code / "replace" / filename,
            base / "zzz_tech_trees" / "replace" / filename,
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        return paths

    def _generate_localization_files_for_language(self, lang_code: str, lang_key: str):
        self._generate_main_tech_tree_file(lang_code, lang_key)
        self._generate_tech_description_replacement_file(lang_code, lang_key)

    def _generate_main_tech_tree_file(self, lang_code: str, lang_key: str):
        file_paths = self._get_output_file_paths(lang_code, f"zztechtreemain_l_{lang_code}.yml")
        lang_config = self.LOCALIZATION_STRINGS[lang_code]
        
        lines = [
            f"{lang_key}:",
            f' technology_tree_title:0 "{lang_config["title"]}"',
            f' tech_tree_max_level:0 "{lang_config["top_level"]}"'
        ]
        
        for tech_id in sorted(self.all_technologies.keys()):
            tree_content = self.generate_tech_tree_content(tech_id, lang_code)
            if tree_content:
                lines.append(f' {tech_id}_techtree:0 "{tree_content}"')
        
        content = '\n'.join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding='utf-8-sig')
            except (OSError, PermissionError) as e:
                print(f"警告：无法写入文件 {file_path}: {e}")

    def _generate_tech_description_replacement_file(self, lang_code: str, lang_key: str):
        file_paths = self._get_output_file_paths(lang_code, f"zztechtreereplaced_l_{lang_code}.yml")
        lines = [f"{lang_key}:"]
        
        missing_descriptions = []
        lang_config = self.LOCALIZATION_STRINGS[lang_code]
        
        for tech_id, tech in sorted(self.all_technologies.items()):
            tech_desc = ""
            if tech_id in self.tech_descriptions and lang_code in self.tech_descriptions[tech_id]:
                tech_desc = self.tech_descriptions[tech_id][lang_code]
            
            if not tech_desc:
                missing_descriptions.append(tech_id)
                tech_desc = ""
            
            tree_content = f"${tech_id}_techtree$"
            if tech_desc:
                full_desc = f"{tech_desc}({lang_config['tier_label']}{tech.tier_level}){tree_content}"
            else:
                full_desc = f"({lang_config['tier_label']}{tech.tier_level}){tree_content}"
            
            lines.append(f' {tech_id}_desc:0 "{full_desc}"')
        
        if missing_descriptions and len(missing_descriptions) > 0:
            print(f"警告: {lang_code} 语言有 {len(missing_descriptions)} 个科技缺失描述")
        
        content = '\n'.join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding='utf-8-sig')
            except (OSError, PermissionError) as e:
                print(f"警告：无法写入文件 {file_path}: {e}")

    def generate_all_yml_files(self):
        output_dir = Path("output/localisation")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for lang_code, lang_key in self.SUPPORTED_LANGUAGES.items():
            self._generate_localization_files_for_language(lang_code, lang_key)
    
    def run_generation_process(self):
        try:
            print("正在生成科技树MOD...")
            self.scan_all_technology_files()
            self.build_technology_tree_relationships()
            self.scan_all_tech_descriptions()
            
            self.display_generation_statistics()
            self.generate_all_yml_files()
            
            print("生成完成！")
            
        except Exception as e:
            print(f"生成过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

    def calculate_generation_statistics(self):
        stats = {
            'total': len(self.all_technologies),
            'base': len(self.base_game_tech_ids),
            'dangerous': sum(1 for t in self.all_technologies.values() if t.is_dangerous_tech),
            'repeatable': sum(1 for t in self.all_technologies.values() if t.is_repeatable_tech),
            'per_area': dict(Counter(t.research_area or 'unknown' for t in self.all_technologies.values())),
            'per_tier': dict(Counter(t.tier_level for t in self.all_technologies.values()))
        }
        stats['mod'] = stats['total'] - stats['base']
        return stats

    def display_generation_statistics(self):
        stats = self.calculate_generation_statistics()
        print(f"\n生成统计:")
        print(f"科技总数: {stats['total']} (本体: {stats['base']}, MOD: {stats['mod']})")
        
        english_count = sum(1 for descs in self.tech_descriptions.values() if "english" in descs)
        chinese_count = sum(1 for descs in self.tech_descriptions.values() if "simp_chinese" in descs)
        print(f"本地化: 英文 {english_count}个, 中文 {chinese_count}个")


def main():
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(application_path, "config.ini")
    
    if not Path(config_path).exists():
        print(f"错误: 配置文件 {config_path} 不存在")
        print("请确保config.ini文件存在并包含正确的路径配置")
        if getattr(sys, 'frozen', False):
            print("\n按 Enter 键退出。")
            input()
        return
        
    generator = TechTreeGenerator(config_path)
    generator.run_generation_process()
    
    if getattr(sys, 'frozen', False):
        print("\n按 Enter 键退出。")
        input()


if __name__ == "__main__":
    main()
