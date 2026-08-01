<script setup>
const emit = defineEmits(['select'])

const groups = [
  {
    title: '其他机构',
    items: [
      '全国社保基金',
      '高毅',
      '中央汇金',
      '香港中央结算',
      '中国证券金融',
      '中国人寿',
      '高盛',
      '中信证券',
      '中金',
      '瑞银',
    ],
  },
  {
    title: '基金',
    items: [
      '招商中证白酒',
      '易方达蓝筹',
      '中欧医疗',
      '兴全合润',
      '景顺长城新兴成长',
      '睿远',
      '富国天惠',
      '广发科技',
    ],
  },
  {
    title: '牛散',
    items: ['谢恺', '徐开东', '赵建平', '葛卫东', '章建平', '吕强', '张素芬', '夏重阳', '魏巍', '洪泽君'],
  },
]

function pick(keyword) {
  emit('select', keyword)
}
</script>

<template>
  <section class="quick-shareholders">
    <div v-for="group in groups" :key="group.title" class="quick-group">
      <span class="quick-group-title">{{ group.title }}</span>
      <div class="quick-chips">
        <button
          v-for="item in group.items"
          :key="item"
          type="button"
          class="quick-chip"
          @click="pick(item)"
        >
          {{ item }}
        </button>
      </div>
    </div>
  </section>
</template>
