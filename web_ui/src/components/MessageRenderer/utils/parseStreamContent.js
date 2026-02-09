/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

/**
 * parseStreamContent - Parse stream content with tags
 * 解析带标签的流式内容
 *
 * @param {string} content - The content to parse
 * @returns {Object} The parsed content
 */
export const parseStreamContent = (content) => {
  if (!content || typeof content !== 'string') {
    return { hasStructure: false, content };
  }

  const hasThoughtStart = content.includes('<reflect>');
  const hasThoughtEnd = content.includes('</reflect>');
  const hasFinalAnswerStart = content.includes('<final_answer>');
  const hasFinalAnswerEnd = content.includes('</final_answer>');

  if (!hasThoughtStart && !hasFinalAnswerStart) {
    return { hasStructure: false, content };
  }

  const segments = [];

  if (hasThoughtStart) {
    let thoughtContent = '';
    if (hasThoughtEnd) {
      const thoughtMatch = content.match(/<reflect>(.*?)<\/reflect>/s);
      if (thoughtMatch) {
        thoughtContent = thoughtMatch[1].trim();
      }
    } else {
      const thoughtStartIndex = content.indexOf('<reflect>');
      if (thoughtStartIndex !== -1) {
        thoughtContent = content.substring(thoughtStartIndex + 9).trim();
      }
    }

    if (thoughtContent) {
      segments.push({
        type: 'reflect',
        content: thoughtContent,
        isComplete: hasThoughtEnd
      });
    }
  }

  if (hasFinalAnswerStart) {
    let finalAnswerContent = '';
    if (hasFinalAnswerEnd) {
      const finalAnswerMatch = content.match(/<final_answer>(.*?)<\/final_answer>/s);
      if (finalAnswerMatch) {
        finalAnswerContent = finalAnswerMatch[1].trim();
      }
    } else {
      const finalAnswerStartIndex = content.indexOf('<final_answer>');
      if (finalAnswerStartIndex !== -1) {
        finalAnswerContent = content.substring(finalAnswerStartIndex + 15).trim();
      }
    }

    if (finalAnswerContent) {
      segments.push({
        type: 'final_answer',
        content: finalAnswerContent,
        isComplete: hasFinalAnswerEnd
      });
    }
  }

  let remainingContent = content;
  if (hasThoughtStart && hasThoughtEnd) {
    remainingContent = remainingContent.replace(/<reflect>.*?<\/reflect>/s, '');
  }
  if (hasFinalAnswerStart && hasFinalAnswerEnd) {
    remainingContent = remainingContent.replace(/<final_answer>.*?<\/final_answer>/s, '');
  }

  if (hasThoughtStart && !hasThoughtEnd) {
    remainingContent = remainingContent.replace(/<reflect>.*$/s, '');
  }
  if (hasFinalAnswerStart && !hasFinalAnswerEnd) {
    remainingContent = remainingContent.replace(/<final_answer>.*$/s, '');
  }

  remainingContent = remainingContent.trim();
  if (remainingContent) {
    segments.push({
      type: 'text',
      content: remainingContent
    });
  }

  return { hasStructure: true, segments };
};
