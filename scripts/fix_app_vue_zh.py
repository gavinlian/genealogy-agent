# -*- coding: utf-8 -*-
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src" / "App.vue"
text = path.read_text(encoding="utf-8")

pairs = [
    ("馃摐", "📜"),
    ("馃摲", "📷"),
    ("脳", "×"),
    ("鈫?", "←"),
    ("鈥?", "–"),
    ("鈥﹀", "…共"),
    ("绗瑊{", "第{{"),
    ("}}浠", "}}代"),
    ("浠ｏ級", "代）"),
    (" 浜?", " 人 ·"),
    ("条″叧绯?", "条关系 ·"),
    (" 浠?", " 代 ·"),
    (" 涓?", " 个"),
    ("缂栬緫", "编辑"),
    ("保存鍒版棌璋", "保存到族谱"),
    ("娴嬭瘯涓", "测试中"),
    ("娴嬭瘯", "测试"),
    ("姝ｅ湪杩炴帴", "正在连接"),
    ("妯″瀷鍥炲", "模型回"),
    ("OCR 璇嗗埆", "OCR 识别"),
    ("妯″瀷鍚嶇О", "模型名称"),
    ("关系瑙ｆ瀽", "关系解析"),
    ("鍏嶈垂", "免费"),
    ("鎵", "扫"),  # careful - might break other chars
]

# safer: only apply unique long strings
safe_pairs = [
    ("<!-- 璁剧疆椤?-->", "<!-- 设置页 -->"),
    ("MiniMax 闇濉?", "MiniMax 需填"),
    (" 鍜?", " 和 "),
    ("Group ID锛堟帶鍒跺彴", "Group ID（控制台"),
    ("placeholder=\"Group ID锛", "placeholder=\"Group ID（"),
    ("<!-- OCR 鎵", "<!-- OCR 扫"),
    ("鎵弿寤鸿氨", "扫描建谱"),
    ("+ 鏂板缓鏃忚氨", "+ 新建族谱"),
    ("鐐瑰嚮鎷嶇収/閫夋嫨鐓х墖", "点击拍照/选择照片"),
    ("寮濮嬭瘑鍒", "开始识别"),
    ("识别结果锛", "识别结果："),
    ("<!-- 娣诲姞/缂栬緫浜虹墿寮圭獥 -->", "<!-- 添加/编辑人物弹窗 -->"),
    ("<!-- 鎵弿缁撴灉鏍℃ -->", "<!-- 扫描结果校正 -->"),
    ("鏍℃鎴愬憳", "校正成员"),
    ("濮撳悕", "姓名"),
    ("涓栦唬", "世代"),
    ("瀛楄緢", "字辈"),
    ("<!-- 鎴愬憳璇︽儏 -->", "<!-- 成员详情 -->"),
    ("瀛楋細", "字："),
    ("鍙凤細", "号："),
    ("绫嶈疮：", "籍贯："),
    ("'纭呭熀娴佸姩'", "'硅基流动'"),
    ("'閫氫箟鍗冮棶'", "'通义千问'"),
    ("'鏅鸿氨 GLM'", "'智谱 GLM'"),
    ("return t || '鍏崇郴'", "return t || '关系'"),
    ("解析结果锛堥粍妗?待核对癸級锛", "解析结果（黄框=待核对）："),
    ("<strong>鑷姩鏃忚氨鏁寸悊</strong>", "<strong>自动族谱整理</strong>"),
    ("鏃忚氨鏍戦瑙堬紙", "族谱树预览（"),
    ("（{{ n.generation }}浠ｏ級", "（{{ n.generation }}代）"),
    ("<span v-if=\"p.generation\">绗瑊{ p.generation }}浠</span>", "<span v-if=\"p.generation\">第{{ p.generation }}代</span>"),
    ("绗瑊{ personDetail.person.generation || '?' }}浠?", "第{{ personDetail.person.generation || '?' }}代"),
    ("ms锛", "ms）"),
]

for a, b in safe_pairs:
    text = text.replace(a, b)

path.write_text(text, encoding="utf-8")
print("done", path)
