elif menu == "Upload Receipt":
    st.header("Upload Receipt Image")
    file = st.file_uploader("Upload receipt image", type=["jpg", "jpeg", "png"], key="receipt_file")
    if file is not None:
        image = Image.open(file).convert("RGB")
        if image.width > 1024:
            ratio = 1024 / float(image.width)
            height = int((float(image.height) * float(ratio)))
            image = image.resize((1024, height), Image.Resampling.LANCZOS)
        os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)
        temp_path = os.path.join(LOCAL_SAVE_DIR, "temp_receipt.png")
        image.save(temp_path)
        with st.spinner("Extracting text from receipt..."):
            text, local_path, category, amount = extract_text_and_save(temp_path)
        if text:
            st.success("Text extracted successfully!")
            st.text_area("Receipt Text", text)
            st.write(f"**Detected Category**: {category}")
            st.write(f"**Detected Amount**: ${amount:.2f}")
        else:
            st.error("Could not process receipt.")
elif menu == "View Summary":
    st.header("Year-End Expense Summary")
    year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year, key="summary_year_v1")
    df = get_summary(year)
    if df is not None and not df.empty:
        st.dataframe(df)
        for category, limit in CATEGORIES.items():
            total = df[df["category"] == category]["amount"].sum()
            st.write(f"{category}: ${total:.2f} / Max Allowed: ${limit}")
    else:
        st.info("No expenses found for the selected year.")