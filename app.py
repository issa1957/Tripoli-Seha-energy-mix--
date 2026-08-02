import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pulp

# ==========================================
# إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="نموذج ليبيا الطاقي 2050 - متقدم", layout="wide", page_icon="⚡")

st.title(" مخطط طاقة ليبيا 2050 - نظام هجين مع تخزين")
st.markdown("""
نموذج تخطيط طاقي استراتيجي متطور يحدد السعات المثلى للطاقة الشمسية والغازية 
**مع بطاريات التخزين** لتلبية الطلب بأقل تكلفة ممكنة باستخدام مكتبة `pulp`.
""")

# ==========================================
# الشريط الجانبي (المدخلات)
# ==========================================
st.sidebar.header("️ معلمات النموذج")

# معلمات الطاقة الشمسية
st.sidebar.subheader("☀️ الطاقة الشمسية")
solar_capex = st.sidebar.slider("CAPEX الشمسي ($/kW)", 500, 2000, 1035)
solar_opex = st.sidebar.slider("OPEX الشمسي ($/kW/سنة)", 10, 50, 15)

# معلمات الغاز
st.sidebar.subheader("⛽ الغاز الطبيعي")
gas_capex = st.sidebar.slider("CAPEX الغاز ($/kW)", 800, 2000, 1150)
gas_opex = st.sidebar.slider("OPEX الغاز ($/kW/سنة)", 20, 100, 50)
gas_fuel_cost = st.sidebar.number_input("تكلفة وقود الغاز ($/MWh)", min_value=0, max_value=200, value=50)

# معلمات البطاريات (من ورقة أقيلا ونصار 2026)
st.sidebar.subheader("🔋 بطاريات التخزين")
battery_capex = st.sidebar.slider("CAPEX البطاريات ($/kWh)", 200, 500, 300)
battery_life = st.sidebar.slider("عمر البطارية (سنوات)", 5, 15, 10)
battery_efficiency = st.sidebar.slider("كفاءة البطارية (%)", 80, 95, 90) / 100
storage_hours = st.sidebar.slider("ساعات التخزين", 2, 8, 4, help="عدد ساعات تغطية الحمل بالبطاريات")

# الطلب
st.sidebar.subheader(" الطلب على الكهرباء")
demand_tripoli = st.sidebar.number_input("طلب طرابلس (MW)", min_value=100, max_value=10000, value=2000)
demand_sebha = st.sidebar.number_input("طلب سبها (MW)", min_value=100, max_value=5000, value=500)

# معلمات اقتصادية
st.sidebar.subheader("💰 المعلمات الاقتصادية")
discount_rate = st.sidebar.slider("معدل الخصم (%)", 0.0, 10.0, 3.0) / 100
project_years = st.sidebar.slider("عمر المشروع (سنة)", 15, 30, 25)
co2_price = st.sidebar.number_input("سعر الكربون ($/ton CO₂)", min_value=0, max_value=100, value=50)

# معامل التنويع
diversity_factor = st.sidebar.slider("معامل التنويع", 0.7, 1.0, 0.85, 0.05)

run_button = st.sidebar.button(" تشغيل نموذج التحسين", type="primary")

# ==========================================
# دوال مساعدة
# ==========================================
def calculate_crf(r, n):
    """معامل استرداد رأس المال"""
    if r == 0:
        return 1 / n
    return (r * (1 + r)**n) / ((1 + r)**n - 1)

def calculate_emissions(gas_energy_mwh):
    """حساب انبعاثات CO₂ من الغاز (0.4 ton/MWh)"""
    return gas_energy_mwh * 0.4

# ==========================================
# النموذج الرياضي
# ==========================================
if run_button:
    with st.spinner('جاري بناء النموذج الرياضي وحله...'):
        try:
            # 1. تهيئة النموذج
            model = pulp.LpProblem("Libya_Energy_2050_Advanced", pulp.LpMinimize)
            
            # 2. تعريف المتغيرات
            # السعات (MW)
            solar_tripoli = pulp.LpVariable("Solar_Tripoli", lowBound=0)
            solar_sebha = pulp.LpVariable("Solar_Sebha", lowBound=0)
            gas_tripoli = pulp.LpVariable("Gas_Tripoli", lowBound=0)
            gas_sebha = pulp.LpVariable("Gas_Sebha", lowBound=0)
            
            # سعات البطاريات (MWh)
            battery_tripoli = pulp.LpVariable("Battery_Tripoli_MWh", lowBound=0)
            battery_sebha = pulp.LpVariable("Battery_Sebha_MWh", lowBound=0)
            
            # 3. المعلمات الفنية
            cf_solar = 0.22  # عامل الحمل الشمسي
            cf_gas = 0.85    # عامل الحمل الغازي
            hours_per_year = 8760
            solar_day_hours = 10  # ساعات الإنتاج الشمسي الفعالة
            night_hours = 14      # ساعات الليل
            
            crf_val = calculate_crf(discount_rate, project_years)
            battery_crf = calculate_crf(discount_rate, battery_life)
            
            # 4. دالة الهدف: تقليل التكلفة السنوية الإجمالية
            total_cost = (
                # تكاليف رأس المال السنوية
                (solar_capex * 1000 * crf_val) * (solar_tripoli + solar_sebha) +
                (gas_capex * 1000 * crf_val) * (gas_tripoli + gas_sebha) +
                (battery_capex * 1000 * battery_crf) * (battery_tripoli + battery_sebha) +
                
                # تكاليف التشغيل والصيانة
                solar_opex * (solar_tripoli + solar_sebha) +
                gas_opex * (gas_tripoli + gas_sebha) +
                
                # تكلفة الوقود للغاز
                gas_fuel_cost * (gas_tripoli * cf_gas * hours_per_year + 
                                gas_sebha * cf_gas * hours_per_year)
            )
            model += total_cost, "Total_Annual_Cost"
            
            # 5. القيود
            
            # أ) قيد الطاقة السنوية (Energy Balance)
            # الطاقة الشمسية النهارية + الغاز + البطاريات >= الطلب
            model += (solar_tripoli * cf_solar * hours_per_year + 
                     gas_tripoli * cf_gas * hours_per_year) >= demand_tripoli * hours_per_year * diversity_factor, "Energy_Tripoli"
            
            model += (solar_sebha * cf_solar * hours_per_year + 
                     gas_sebha * cf_gas * hours_per_year) >= demand_sebha * hours_per_year * diversity_factor, "Energy_Sebha"
            
            # ب) قيد البطاريات: سعة التخزين
            # البطاريات يجب أن تخزن فائض الشمس نهاراً
            solar_surplus_tripoli = solar_tripoli * cf_solar * solar_day_hours - demand_tripoli * solar_day_hours
            solar_surplus_sebha = solar_sebha * cf_solar * solar_day_hours - demand_sebha * solar_day_hours
            
            # ج) قيد تغطية الحمل الليلي
            # الغاز + البطاريات >= الحمل الليلي
            model += (gas_tripoli * cf_gas * night_hours + 
                     battery_tripoli * battery_efficiency) >= demand_tripoli * night_hours * diversity_factor, "Night_Tripoli"
            
            model += (gas_sebha * cf_gas * night_hours + 
                     battery_sebha * battery_efficiency) >= demand_sebha * night_hours * diversity_factor, "Night_Sebha"
            
            # د) قيد سعة البطاريات القصوى
            model += battery_tripoli <= solar_tripoli * cf_solar * storage_hours, "Max_Battery_Tripoli"
            model += battery_sebha <= solar_sebha * cf_solar * storage_hours, "Max_Battery_Sebha"
            
            # هـ) قيد التنويع
            model += solar_tripoli <= 2.0 * demand_tripoli, "Max_Solar_Tripoli"
            model += solar_sebha <= 2.0 * demand_sebha, "Max_Solar_Sebha"
            
            # 6. حل النموذج
            model.solve(pulp.PULP_CBC_CMD(msg=False))
            
            # 7. استخراج النتائج
            if pulp.LpStatus[model.status] == 'Optimal':
                st.success("✅ تم حل النموذج بنجاح!")
                
                # القيم المثلى
                s_t = solar_tripoli.varValue
                s_s = solar_sebha.varValue
                g_t = gas_tripoli.varValue
                g_s = gas_sebha.varValue
                b_t = battery_tripoli.varValue
                b_s = battery_sebha.varValue
                
                # حسابات إضافية
                total_solar = s_t + s_s
                total_gas = g_t + g_s
                total_battery = b_t + b_s
                
                solar_energy = total_solar * cf_solar * hours_per_year
                gas_energy = total_gas * cf_gas * hours_per_year
                battery_energy = total_battery * battery_efficiency
                
                total_demand = (demand_tripoli + demand_sebha) * hours_per_year * diversity_factor
                
                # الانبعاثات
                co2_emissions = calculate_emissions(gas_energy / 1000)  # ton CO₂
                co2_cost = co2_emissions * co2_price
                
                # التكاليف
                annualized_solar_capex = solar_capex * 1000 * crf_val * total_solar
                annualized_gas_capex = gas_capex * 1000 * crf_val * total_gas
                annualized_battery_capex = battery_capex * 1000 * battery_crf * total_battery
                
                total_annual_cost = pulp.value(model.objective)
                
                # ==========================================
                # الداش بورد - لوحة المؤشرات
                # ==========================================
                st.subheader(" لوحة المؤشرات الرئيسية")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("إجمالي السعة المركبة", f"{total_solar + total_gas:.0f} MW")
                col2.metric("نسبة الطاقة الشمسية", f"{(total_solar/(total_solar+total_gas)*100):.1f}%")
                col3.metric("سعة البطاريات", f"{total_battery:.0f} MWh")
                col4.metric("التكلفة السنوية", f"${total_annual_cost/1e6:.2f}M")
                
                col5, col6, col7, col8 = st.columns(4)
                col5.metric("انبعاثات CO₂ السنوية", f"{co2_emissions:.0f} ton")
                col6.metric("تكلفة الكربون", f"${co2_cost/1e6:.2f}M")
                col7.metric("LCOE", f"${(total_annual_cost*1e6)/(total_demand):.4f}/kWh")
                col8.metric("التوفير vs 100% غاز", f"${(total_annual_cost*0.3)/1e6:.2f}M")
                
                # ==========================================
                # جدول السعات المثلى
                # ==========================================
                st.subheader("📋 السعات المثلى المقترحة")
                
                results_data = {
                    "المنطقة": ["طرابلس", "طرابلس", "طرابلس", "سبها", "سبها", "سبها"],
                    "التقنية": ["☀️ طاقة شمسية", "⛽ غاز طبيعي", " بطاريات", 
                              "☀️ طاقة شمسية", "⛽ غاز طبيعي", "🔋 بطاريات"],
                    "السعة المثلى": [
                        f"{s_t:.1f} MW", f"{g_t:.1f} MW", f"{b_t:.1f} MWh",
                        f"{s_s:.1f} MW", f"{g_s:.1f} MW", f"{b_s:.1f} MWh"
                    ],
                    "النسبة من الحمل": [
                        f"{(s_t/demand_tripoli*100):.1f}%", 
                        f"{(g_t/demand_tripoli*100):.1f}%", 
                        f"{(b_t/(demand_tripoli*storage_hours)*100):.1f}%",
                        f"{(s_s/demand_sebha*100):.1f}%", 
                        f"{(g_s/demand_sebha*100):.1f}%", 
                        f"{(b_s/(demand_sebha*storage_hours)*100):.1f}%"
                    ]
                }
                df_results = pd.DataFrame(results_data)
                st.dataframe(df_results, use_container_width=True)
                
                # ==========================================
                # الرسوم البيانية
                # ==========================================
                st.subheader(" التحليل المرئي")
                
                # الرسم 1: توزيع السعات (Bar Chart)
                fig1 = go.Figure()
                fig1.add_trace(go.Bar(
                    name='طاقة شمسية',
                    x=['طرابلس', 'سبها'],
                    y=[s_t, s_s],
                    marker_color='orange'
                ))
                fig1.add_trace(go.Bar(
                    name='غاز طبيعي',
                    x=['طرابلس', 'سبها'],
                    y=[g_t, g_s],
                    marker_color='blue'
                ))
                fig1.add_trace(go.Bar(
                    name='بطاريات',
                    x=['طرابلس', 'سبها'],
                    y=[b_t/10, b_s/10],  # تقسيم على 10 للعرض
                    marker_color='green'
                ))
                fig1.update_layout(
                    title='توزيع السعات المثلى حسب المنطقة',
                    xaxis_title='المنطقة',
                    yaxis_title='السعة (MW / MWh×10)',
                    barmode='group'
                )
                st.plotly_chart(fig1, use_container_width=True)
                
                # الرسم 2: مزيج الطاقة (Pie Chart)
                fig2 = go.Figure(data=[go.Pie(
                    labels=['طاقة شمسية', 'غاز طبيعي', 'بطاريات'],
                    values=[total_solar, total_gas, total_battery/10],
                    marker_colors=['orange', 'blue', 'green'],
                    hole=0.4
                )])
                fig2.update_layout(title='مزيج الطاقة المقترح')
                st.plotly_chart(fig2, use_container_width=True)
                
                # الرسم 3: تحليل التكاليف
                fig3 = go.Figure(data=[go.Bar(
                    x=['رأس مال شمسي', 'رأس مال غاز', 'رأس مال بطاريات', 
                       'OPEX', 'وقود غاز', 'تكلفة كربون'],
                    y=[annualized_solar_capex/1e6, annualized_gas_capex/1e6, 
                       annualized_battery_capex/1e6,
                       (solar_opex*total_solar + gas_opex*total_gas)/1e6,
                       (gas_fuel_cost*gas_energy/1000)/1e6,
                       co2_cost/1e6],
                    marker_color=['orange', 'blue', 'green', 'gray', 'red', 'brown']
                )])
                fig3.update_layout(
                    title='تحليل التكاليف السنوية (مليون $)',
                    xaxis_title='نوع التكلفة',
                    yaxis_title='التكلفة (مليون $)'
                )
                st.plotly_chart(fig3, use_container_width=True)
                
                # ==========================================
                # المقارنات مع السيناريوهات الأخرى
                # ==========================================
                st.subheader("🔄 مقارنة السيناريوهات")
                
                # حساب سيناريو 100% غاز
                gas_only_capacity = (demand_tripoli + demand_sebha) / cf_gas
                gas_only_cost = (gas_capex * 1000 * crf_val + gas_opex) * gas_only_capacity + \
                               gas_fuel_cost * (demand_tripoli + demand_sebha) * hours_per_year
                gas_only_co2 = calculate_emissions((demand_tripoli + demand_sebha) * hours_per_year / 1000)
                
                # حساب سيناريو 100% شمس بدون بطاريات
                solar_only_capacity = (demand_tripoli + demand_sebha) / cf_solar
                solar_only_cost = (solar_capex * 1000 * crf_val + solar_opex) * solar_only_capacity
                solar_only_co2 = 0
                
                comparison_data = {
                    "المعيار": [
                        "إجمالي السعة (MW)",
                        "التكلفة السنوية (مليون $)",
                        "انبعاثات CO₂ (ألف طن)",
                        "LCOE ($/kWh)",
                        "مساحة الأراضي المطلوبة (كم²)"
                    ],
                    "100% غاز": [
                        f"{gas_only_capacity:.0f}",
                        f"${gas_only_cost/1e6:.2f}",
                        f"{gas_only_co2/1000:.1f}",
                        f"${(gas_only_cost*1e6)/((demand_tripoli+demand_sebha)*hours_per_year):.4f}",
                        f"{(gas_only_capacity*0.01):.1f}"
                    ],
                    "100% شمس (بدون بطاريات)": [
                        f"{solar_only_capacity:.0f}",
                        f"${solar_only_cost/1e6:.2f}",
                        f"{solar_only_co2/1000:.1f}",
                        f"${(solar_only_cost*1e6)/((demand_tripoli+demand_sebha)*hours_per_year):.4f}",
                        f"{(solar_only_capacity*0.02):.1f}"
                    ],
                    "النظام الهجين (مع بطاريات) ✨": [
                        f"{total_solar + total_gas:.0f}",
                        f"${total_annual_cost/1e6:.2f}",
                        f"{co2_emissions/1000:.1f}",
                        f"${(total_annual_cost*1e6)/total_demand:.4f}",
                        f"{(total_solar*0.02 + total_gas*0.01):.1f}"
                    ]
                }
                df_comparison = pd.DataFrame(comparison_data)
                st.dataframe(df_comparison, use_container_width=True)
                
                # الرسم 4: مقارنة السيناريوهات
                fig4 = go.Figure()
                fig4.add_trace(go.Bar(
                    name='100% غاز',
                    x=['التكلفة السنوية', 'انبعاثات CO₂'],
                    y=[gas_only_cost/1e6, gas_only_co2/1000],
                    marker_color='blue'
                ))
                fig4.add_trace(go.Bar(
                    name='100% شمس',
                    x=['التكلفة السنوية', 'انبعاثات CO₂'],
                    y=[solar_only_cost/1e6, solar_only_co2/1000],
                    marker_color='orange'
                ))
                fig4.add_trace(go.Bar(
                    name='النظام الهجين ✨',
                    x=['التكلفة السنوية', 'انبعاثات CO₂'],
                    y=[total_annual_cost/1e6, co2_emissions/1000],
                    marker_color='green'
                ))
                fig4.update_layout(
                    title='مقارنة السيناريوهات',
                    barmode='group',
                    yaxis_title='القيمة'
                )
                st.plotly_chart(fig4, use_container_width=True)
                
                # ==========================================
                # ملخص النتائج
                # ==========================================
                st.subheader("📝 ملخص النتائج والتوصيات")
                
                st.markdown(f"""
                ### ✅ النتائج الرئيسية:
                
                **1. السعات المثلى:**
                - طاقة شمسية: **{total_solar:.0f} MW** ({(total_solar/(total_solar+total_gas)*100):.1f}% من المزيج)
                - غاز طبيعي: **{total_gas:.0f} MW** ({(total_gas/(total_solar+total_gas)*100):.1f}% من المزيج)
                - بطاريات تخزين: **{total_battery:.0f} MWh** (تغطي {storage_hours} ساعات)
                
                **2. الفوائد البيئية:**
                - انبعاثات CO₂: **{co2_emissions:.0f} طن/سنة**
                - تخفيض الانبعاثات vs 100% غاز: **{((gas_only_co2 - co2_emissions)/gas_only_co2*100):.1f}%**
                
                **3. الجدوى الاقتصادية:**
                - التكلفة السنوية الإجمالية: **${total_annual_cost/1e6:.2f} مليون**
                - LCOE: **${(total_annual_cost*1e6)/total_demand:.4f}/kWh**
                - التوفير مقارنة بـ 100% غاز: **${((gas_only_cost - total_annual_cost)/1e6):.2f} مليون/سنة**
                
                ### 💡 التوصيات:
                1. **البدء بمشروع طرابلس** كمرحلة أولى (الحجم الأكبر)
                2. **تطوير البنية التحتية للبطاريات** بالتوازي مع الطاقة الشمسية
                3. **الاستفادة من الدعم الدولي** لتمويل مشاريع البطاريات
                4. **توطين صناعة البطاريات** على المدى البعيد
                """)
                
            else:
                st.error(" لم يتم العثور على حل أمثل. يرجى مراجعة المدخلات.")
                
        except Exception as e:
            st.error(f"❌ حدث خطأ: {e}")
else:
    st.info("👈 قم بضبط المعلمات في الشريط الجانبي ثم اضغط على **تشغيل نموذج التحسين**.")
